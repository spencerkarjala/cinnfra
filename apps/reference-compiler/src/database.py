from datetime import datetime, timezone

import aiosqlite

from config import DATABASE_PATH


async def init_database():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS art_references (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                artist TEXT NOT NULL,
                track_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def find_existing_reference(url: str, media_type: str) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE art_references
            SET artist = ?, track_name = ?, fetched_at = ?
            WHERE id = ?
            """,
            (artist, track_name, datetime.now(timezone.utc).isoformat(), reference_id),
        )
        await db.commit()


async def get_all_references() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM art_references ORDER BY fetched_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def delete_reference(reference_id: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM art_references WHERE id = ?", (reference_id,))
        await db.commit()
        return cursor.rowcount > 0
