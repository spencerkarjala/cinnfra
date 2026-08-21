import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from config import BOARDS_DATABASE_PATH, REFERENCES_DATABASE_PATH


@asynccontextmanager
async def connect_boards_database():
    async with aiosqlite.connect(BOARDS_DATABASE_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")
        yield db


async def init_database() -> None:
    BOARDS_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with connect_boards_database() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS boards (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS board_items (
                id TEXT PRIMARY KEY,
                board_id TEXT NOT NULL,
                reference_id TEXT NOT NULL,
                position_x REAL NOT NULL,
                position_y REAL NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE
            )
        """)
        await db.commit()


async def get_all_references() -> list[dict]:
    if not REFERENCES_DATABASE_PATH.exists():
        return []

    try:
        async with aiosqlite.connect(REFERENCES_DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM art_references ORDER BY fetched_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                references = [dict(row) | {"tags": []} for row in rows]

            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reference_tags'"
            ) as cursor:
                has_tags = await cursor.fetchone() is not None

            if not has_tags or not references:
                return references

            references_by_id = {
                reference["id"]: reference for reference in references
            }
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
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return []
        raise


async def get_all_boards() -> list[dict]:
    async with connect_boards_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM boards ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_board(board_id: str) -> dict | None:
    async with connect_boards_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM boards WHERE id = ?", (board_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_board(board_id: str, name: str) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    async with connect_boards_database() as db:
        await db.execute(
            "INSERT INTO boards (id, name, created_at) VALUES (?, ?, ?)",
            (board_id, name, created_at),
        )
        await db.commit()
    return {"id": board_id, "name": name, "created_at": created_at}


async def delete_board(board_id: str) -> bool:
    async with connect_boards_database() as db:
        cursor = await db.execute("DELETE FROM boards WHERE id = ?", (board_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_board_items(board_id: str) -> list[dict]:
    async with connect_boards_database() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM board_items WHERE board_id = ? ORDER BY rowid",
            (board_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_board_item(
    item_id: str,
    board_id: str,
    reference_id: str,
    position_x: float,
    position_y: float,
    width: float,
    height: float,
) -> None:
    async with connect_boards_database() as db:
        await db.execute(
            """
            INSERT INTO board_items (
                id, board_id, reference_id, position_x, position_y, width, height
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                board_id,
                reference_id,
                position_x,
                position_y,
                width,
                height,
            ),
        )
        await db.commit()


async def replace_board_items(board_id: str, items: list[dict]) -> None:
    async with connect_boards_database() as db:
        await db.execute("DELETE FROM board_items WHERE board_id = ?", (board_id,))
        if items:
            await db.executemany(
                """
                INSERT INTO board_items (
                    id, board_id, reference_id, position_x, position_y, width, height
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["id"],
                        board_id,
                        item["reference_id"],
                        item["position_x"],
                        item["position_y"],
                        item["width"],
                        item["height"],
                    )
                    for item in items
                ],
            )
        await db.commit()


async def delete_board_item(board_id: str, item_id: str) -> bool:
    async with connect_boards_database() as db:
        cursor = await db.execute(
            "DELETE FROM board_items WHERE id = ? AND board_id = ?",
            (item_id, board_id),
        )
        await db.commit()
        return cursor.rowcount > 0
