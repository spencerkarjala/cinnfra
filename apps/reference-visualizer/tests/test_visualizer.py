import os
import sys
import tempfile
import unittest
from pathlib import Path

import aiosqlite
import httpx


TEST_DIRECTORY = tempfile.TemporaryDirectory()
APP_ROOT = Path(__file__).parents[1]
os.environ["REFERENCES_DATABASE_PATH"] = str(
    Path(TEST_DIRECTORY.name) / "references.db"
)
os.environ["BOARDS_DATABASE_PATH"] = str(Path(TEST_DIRECTORY.name) / "boards.db")
os.environ["ARTWORK_DIR"] = TEST_DIRECTORY.name
os.environ["STATIC_DIR"] = str(APP_ROOT / "static")
sys.path.insert(0, str(APP_ROOT / "server"))

import database  # noqa: E402
from main import app  # noqa: E402


class VisualizerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Path(os.environ["REFERENCES_DATABASE_PATH"]).unlink(missing_ok=True)
        Path(os.environ["BOARDS_DATABASE_PATH"]).unlink(missing_ok=True)
        await self.create_reference_database()
        await database.init_database()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def create_reference_database(self):
        async with aiosqlite.connect(os.environ["REFERENCES_DATABASE_PATH"]) as db:
            await db.executescript("""
                CREATE TABLE art_references (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    track_name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE tags (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL
                );
                CREATE TABLE reference_tags (
                    reference_id TEXT NOT NULL,
                    tag_id TEXT NOT NULL
                );
                INSERT INTO art_references VALUES (
                    'reference-1', 'https://example.com/image.jpg', 'Artist',
                    'Image', 'DIRECT_MEDIA_IMAGE', 'reference-1.jpg',
                    '2026-01-01T00:00:00+00:00'
                );
                INSERT INTO tags VALUES ('tag-1', 'Architecture');
                INSERT INTO reference_tags VALUES ('reference-1', 'tag-1');
            """)
            await db.commit()

    async def test_static_application_and_tagged_references(self):
        page = await self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Reference Visualizer", page.text)
        self.assertIn("/app.js", page.text)

        response = await self.client.get("/api/references")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], "reference-1")
        self.assertEqual(
            response.json()[0]["tags"],
            [{"id": "tag-1", "display_name": "Architecture"}],
        )

    async def test_board_create_replace_load_and_delete(self):
        create_response = await self.client.post(
            "/api/boards", json={"name": "  Exterior studies  "}
        )
        self.assertEqual(create_response.status_code, 201)
        board = create_response.json()
        self.assertEqual(board["name"], "Exterior studies")

        item = {
            "id": "item-1",
            "reference_id": "reference-1",
            "position_x": 100,
            "position_y": 125,
            "width": 320,
            "height": 240,
        }
        update_response = await self.client.put(
            f"/api/boards/{board['id']}/items", json={"items": [item]}
        )
        self.assertEqual(update_response.json(), {"updated": 1})

        get_response = await self.client.get(f"/api/boards/{board['id']}")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["items"], [item])

        clear_response = await self.client.put(
            f"/api/boards/{board['id']}/items", json={"items": []}
        )
        self.assertEqual(clear_response.json(), {"updated": 0})
        self.assertEqual(
            (await self.client.get(f"/api/boards/{board['id']}")).json()["items"],
            [],
        )

        await self.client.post(f"/api/boards/{board['id']}/items", json=item)
        delete_response = await self.client.delete(f"/api/boards/{board['id']}")
        self.assertEqual(delete_response.status_code, 200)

        async with database.connect_boards_database() as db:
            async with db.execute("SELECT COUNT(*) FROM board_items") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 0)

    async def test_item_validation_and_missing_board(self):
        invalid_item = {
            "id": "item-1",
            "reference_id": "reference-1",
            "position_x": 0,
            "position_y": 0,
            "width": 0,
            "height": 100,
        }
        response = await self.client.put(
            "/api/boards/missing/items", json={"items": [invalid_item]}
        )
        self.assertEqual(response.status_code, 422)

        response = await self.client.put(
            "/api/boards/missing/items", json={"items": []}
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
