import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx


TEST_DIRECTORY = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(TEST_DIRECTORY.name) / "references.db")
os.environ["OUTPUT_DIR"] = TEST_DIRECTORY.name
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import database  # noqa: E402
from core.fetcher import download_image  # noqa: E402
from core.reference import process_url  # noqa: E402
from main import app  # noqa: E402


DIRECT_IMAGE_URL = (
    "https://www.maquetland.com/upload/phototeque/images/18730/"
    "9S80_ppru1_ovod%20_mtllbu%20(1).jpg"
)


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


if __name__ == "__main__":
    unittest.main()
