from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from config import DATABASE_PATH


@asynccontextmanager
async def connect_database():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def init_database():
    async with connect_database() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS art_references (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                artist TEXT NOT NULL,
                track_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL
            )
        """)
        async with db.execute("PRAGMA table_info(art_references)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "notes" not in columns:
            await db.execute(
                "ALTER TABLE art_references ADD COLUMN notes TEXT NOT NULL DEFAULT ''"
            )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL COLLATE NOCASE UNIQUE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reference_tags (
                reference_id TEXT NOT NULL,
                tag_id TEXT NOT NULL,
                PRIMARY KEY (reference_id, tag_id),
                FOREIGN KEY (reference_id) REFERENCES art_references(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)
        await db.commit()


async def find_existing_reference(url: str, media_type: str) -> dict | None:
    async with connect_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM art_references WHERE url = ? AND media_type = ?",
            (url, media_type),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def save_reference(
    reference_id: str,
    url: str,
    artist: str,
    track_name: str,
    media_type: str,
    filename: str,
) -> None:
    async with connect_database() as db:
        await db.execute(
            """
            INSERT INTO art_references (id, url, artist, track_name, media_type, filename, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (reference_id, url, artist, track_name, media_type, filename, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def update_reference(
    reference_id: str,
    artist: str,
    track_name: str,
) -> None:
    async with connect_database() as db:
        await db.execute(
            """
            UPDATE art_references
            SET artist = ?, track_name = ?, fetched_at = ?
            WHERE id = ?
            """,
            (artist, track_name, datetime.now(timezone.utc).isoformat(), reference_id),
        )
        await db.commit()


async def update_reference_notes(reference_id: str, notes: str) -> bool:
    async with connect_database() as db:
        cursor = await db.execute(
            "UPDATE art_references SET notes = ? WHERE id = ?",
            (notes, reference_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_all_references() -> list[dict]:
    async with connect_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM art_references ORDER BY fetched_at DESC") as cursor:
            rows = await cursor.fetchall()
            references = [dict(row) | {"tags": []} for row in rows]

        references_by_id = {reference["id"]: reference for reference in references}
        async with db.execute("""
            SELECT reference_tags.reference_id, tags.id, tags.display_name
            FROM reference_tags
            JOIN tags ON tags.id = reference_tags.tag_id
            ORDER BY tags.display_name COLLATE NOCASE
        """) as cursor:
            tag_rows = await cursor.fetchall()

        for row in tag_rows:
            reference = references_by_id.get(row["reference_id"])
            if reference is not None:
                reference["tags"].append({
                    "id": row["id"],
                    "display_name": row["display_name"],
                })

        return references


async def get_reference(reference_id: str) -> dict | None:
    async with connect_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM art_references WHERE id = ?", (reference_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def delete_reference(reference_id: str) -> bool:
    async with connect_database() as db:
        cursor = await db.execute("DELETE FROM art_references WHERE id = ?", (reference_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_all_tags() -> list[dict]:
    async with connect_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, display_name FROM tags ORDER BY display_name COLLATE NOCASE"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def create_tag(tag_id: str, display_name: str) -> dict:
    async with connect_database() as db:
        await db.execute(
            "INSERT INTO tags (id, display_name) VALUES (?, ?)",
            (tag_id, display_name),
        )
        await db.commit()
    return {"id": tag_id, "display_name": display_name}


async def update_tag(tag_id: str, display_name: str) -> dict | None:
    async with connect_database() as db:
        cursor = await db.execute(
            "UPDATE tags SET display_name = ? WHERE id = ?",
            (display_name, tag_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
    return {"id": tag_id, "display_name": display_name}


async def delete_tag(tag_id: str) -> bool:
    async with connect_database() as db:
        cursor = await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        await db.commit()
        return cursor.rowcount > 0


async def set_reference_tags(reference_id: str, tag_ids: list[str]) -> list[dict] | None:
    # Deduplication makes the operation tolerant of repeated IDs while the
    # composite primary key keeps the stored relationship minimal.
    unique_tag_ids = list(dict.fromkeys(tag_ids))

    async with connect_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT 1 FROM art_references WHERE id = ?", (reference_id,)
        ) as cursor:
            if await cursor.fetchone() is None:
                return None

        tags = []
        if unique_tag_ids:
            placeholders = ",".join("?" for _ in unique_tag_ids)
            async with db.execute(
                f"SELECT id, display_name FROM tags WHERE id IN ({placeholders})",
                unique_tag_ids,
            ) as cursor:
                rows = await cursor.fetchall()
                tags = [dict(row) for row in rows]

            found_ids = {tag["id"] for tag in tags}
            missing_ids = [tag_id for tag_id in unique_tag_ids if tag_id not in found_ids]
            if missing_ids:
                raise ValueError(f"Unknown tag IDs: {', '.join(missing_ids)}")

        await db.execute("DELETE FROM reference_tags WHERE reference_id = ?", (reference_id,))
        if unique_tag_ids:
            await db.executemany(
                "INSERT INTO reference_tags (reference_id, tag_id) VALUES (?, ?)",
                [(reference_id, tag_id) for tag_id in unique_tag_ids],
            )
        await db.commit()

    return sorted(tags, key=lambda tag: tag["display_name"].casefold())
