import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import aiosqlite


TEST_DIRECTORY = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(TEST_DIRECTORY.name) / "references.db")
os.environ["OUTPUT_DIR"] = TEST_DIRECTORY.name
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import database  # noqa: E402
from core.fetcher import download_image  # noqa: E402
from core.reference import process_url  # noqa: E402
from handlers.x import XHandler  # noqa: E402
from main import app  # noqa: E402


DIRECT_IMAGE_URL = (
    "https://www.maquetland.com/upload/phototeque/images/18730/"
    "9S80_ppru1_ovod%20_mtllbu%20(1).jpg"
)
X_VIDEO_URL = "https://x.com/artofallan/status/2043000140236243359/video/1"


class ReferenceCompilerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Path(os.environ["DATABASE_PATH"]).unlink(missing_ok=True)
        await database.init_database()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_tag_crud_and_atomic_reference_assignment(self):
        await database.save_reference(
            "reference-1",
            "https://example.com/image.jpg",
            "Example",
            "image.jpg",
            "DIRECT_MEDIA_IMAGE",
            "reference-1.jpg",
        )

        create_response = await self.client.post(
            "/tags", json={"display_name": "  Architecture  "}
        )
        self.assertEqual(create_response.status_code, 201)
        tag = create_response.json()
        self.assertEqual(tag["display_name"], "Architecture")

        duplicate_response = await self.client.post(
            "/tags", json={"display_name": "architecture"}
        )
        self.assertEqual(duplicate_response.status_code, 409)

        rename_response = await self.client.patch(
            f"/tags/{tag['id']}", json={"display_name": "Buildings"}
        )
        self.assertEqual(rename_response.status_code, 200)
        self.assertEqual(rename_response.json()["display_name"], "Buildings")

        assignment_response = await self.client.put(
            "/reference/reference-1/tags",
            json={"tag_ids": [tag["id"], tag["id"]]},
        )
        self.assertEqual(assignment_response.status_code, 200)
        self.assertEqual(assignment_response.json(), [rename_response.json()])

        references = await database.get_all_references()
        self.assertEqual(references[0]["tags"], [rename_response.json()])

        page_response = await self.client.get("/")
        self.assertIn("+ Add tag", page_response.text)
        self.assertIn("Buildings", page_response.text)
        self.assertIn("Apply", page_response.text)
        self.assertIn('id="media-dialog"', page_response.text)
        self.assertIn('class="preview-image"', page_response.text)

        delete_response = await self.client.delete(f"/tags/{tag['id']}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual((await database.get_all_references())[0]["tags"], [])

    async def test_assignment_rejects_unknown_ids_without_changing_tags(self):
        await database.save_reference(
            "reference-1", "https://example.com/a.jpg", "", "a.jpg", "DIRECT_MEDIA_IMAGE", "a.jpg"
        )
        tag_response = await self.client.post("/tags", json={"display_name": "Valid"})
        tag_id = tag_response.json()["id"]
        await self.client.put(
            "/reference/reference-1/tags", json={"tag_ids": [tag_id]}
        )

        response = await self.client.put(
            "/reference/reference-1/tags", json={"tag_ids": ["missing"]}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            (await database.get_all_references())[0]["tags"][0]["id"], tag_id
        )

    async def test_direct_image_url_is_compiled(self):
        with patch("core.reference.download_image", new=AsyncMock()):
            responses = await process_url(DIRECT_IMAGE_URL)

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].media_type, "DIRECT_MEDIA_IMAGE")
        self.assertEqual(responses[0].filename.rsplit(".", 1)[-1], "jpg")
        self.assertEqual(responses[0].artist, "www.maquetland.com")
        self.assertEqual(
            responses[0].track_name, "9S80_ppru1_ovod _mtllbu (1).jpg"
        )

    async def test_x_post_imports_every_video_at_the_best_quality(self):
        response = {
            "id_str": "2043000140236243359",
            "text": "A compact Blender workflow https://t.co/example",
            "display_text_range": [0, 26],
            "user": {"screen_name": "artofallan", "name": "Broke My Pencil"},
            "mediaDetails": [
                {
                    "type": "video",
                    "video_info": {
                        "variants": [
                            {
                                "content_type": "application/x-mpegURL",
                                "url": "https://video.twimg.com/first.m3u8",
                            },
                            {
                                "bitrate": 432000,
                                "content_type": "video/mp4",
                                "url": "https://video.twimg.com/first-small.mp4",
                            },
                            {
                                "bitrate": 1280000,
                                "content_type": "video/mp4",
                                "url": "https://video.twimg.com/first-large.mp4",
                            },
                        ]
                    },
                },
                {
                    "type": "video",
                    "video_info": {
                        "variants": [
                            {
                                "bitrate": 832000,
                                "content_type": "video/mp4",
                                "url": "https://video.twimg.com/second.mp4",
                            }
                        ]
                    },
                },
            ],
        }

        with patch(
            "handlers.x.fetch_page_content",
            new=AsyncMock(return_value=json.dumps(response)),
        ) as fetch:
            results = await XHandler().fetch_artwork(X_VIDEO_URL)

        self.assertIn("id=2043000140236243359", fetch.await_args.args[0])
        self.assertEqual(
            [result.image_url for result in results],
            [
                "https://video.twimg.com/first-large.mp4",
                "https://video.twimg.com/second.mp4",
            ],
        )
        self.assertEqual(
            [result.media_type for result in results],
            ["X_POST_VIDEO", "X_POST_VIDEO_1"],
        )
        self.assertEqual(results[0].artist, "artofallan")
        self.assertEqual(results[0].track_name, "A compact Blender workflow")

    async def test_x_handler_supports_twitter_urls_and_images(self):
        handler = XHandler()
        self.assertTrue(handler.can_handle(X_VIDEO_URL))
        self.assertTrue(
            handler.can_handle(
                "https://twitter.com/artofallan/status/2043000140236243359"
            )
        )

        response = {
            "id_str": "123",
            "text": "Reference image",
            "user": {"name": "An Artist"},
            "mediaDetails": [
                {"type": "photo", "media_url_https": "https://pbs.twimg.com/a.jpg"}
            ],
        }
        with patch(
            "handlers.x.fetch_page_content",
            new=AsyncMock(return_value=json.dumps(response)),
        ):
            results = await handler.fetch_artwork("https://x.com/example/status/123")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].media_type, "X_POST_IMAGE")
        self.assertEqual(results[0].artist, "An Artist")

    async def test_download_retries_http_for_a_bad_https_certificate(self):
        class FakeClient:
            def __init__(self):
                self.requested_urls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url, follow_redirects):
                self.requested_urls.append(url)
                if url.startswith("https://"):
                    raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")
                return httpx.Response(
                    200, content=b"image bytes", request=httpx.Request("GET", url)
                )

        fake_client = FakeClient()
        output_path = Path(TEST_DIRECTORY.name) / "downloaded.jpg"
        with patch("core.fetcher.httpx.AsyncClient", return_value=fake_client) as client:
            await download_image(DIRECT_IMAGE_URL, output_path)

        self.assertEqual(
            fake_client.requested_urls,
            [DIRECT_IMAGE_URL, DIRECT_IMAGE_URL.replace("https://", "http://", 1)],
        )
        self.assertEqual(output_path.read_bytes(), b"image bytes")
        self.assertIn("Mozilla/5.0", client.call_args.kwargs["headers"]["User-Agent"])

    async def test_form_posts_redirect_to_a_get(self):
        response = await self.client.post(
            "/", data={"url": "https://example.com/unsupported"}
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/?error=Unsupported+URL.")
        redirected_page = await self.client.get(response.headers["location"])
        self.assertEqual(redirected_page.status_code, 200)
        self.assertIn("Unsupported URL.", redirected_page.text)

        delete_response = await self.client.post("/delete/missing")
        self.assertEqual(delete_response.status_code, 303)
        self.assertEqual(delete_response.headers["location"], "/")

    async def test_unicode_reference_notes(self):
        await database.save_reference(
            "reference-1",
            "https://example.com/image.jpg",
            "Example",
            "image.jpg",
            "DIRECT_MEDIA_IMAGE",
            "reference-1.jpg",
        )
        notes = "我喜欢这个轮廓 — très beau 🚀\nKeep the <strong>contrast</strong>."

        response = await self.client.patch(
            "/reference/reference-1/notes", json={"notes": notes}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reference_id": "reference-1", "notes": notes})
        self.assertEqual((await database.get_all_references())[0]["notes"], notes)

        page = await self.client.get("/")
        self.assertIn("我喜欢这个轮廓 — très beau 🚀", page.text)
        self.assertIn("&lt;strong&gt;contrast&lt;/strong&gt;", page.text)
        self.assertNotIn("<strong>contrast</strong>", page.text)

    async def test_existing_database_gets_notes_column(self):
        database_path = Path(os.environ["DATABASE_PATH"])
        database_path.unlink()
        async with aiosqlite.connect(database_path) as db:
            await db.execute("""
                CREATE TABLE art_references (
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

        await database.init_database()

        async with aiosqlite.connect(database_path) as db:
            async with db.execute("PRAGMA table_info(art_references)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
        self.assertIn("notes", columns)


if __name__ == "__main__":
    unittest.main()
