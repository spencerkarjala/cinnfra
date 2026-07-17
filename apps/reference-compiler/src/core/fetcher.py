from pathlib import Path
from urllib.parse import urlparse

import httpx


async def fetch_page_content(url: str, headers: dict[str, str] | None = None) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True, headers=headers)
        response.raise_for_status()
        return response.text


async def download_image(image_url: str, output_path: Path) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url, follow_redirects=True)
        response.raise_for_status()
        output_path.write_bytes(response.content)


def image_extension(image_url: str) -> str:
    # CDN URLs (eg. Instagram's) carry signing query params, so the extension
    # has to come from the URL path rather than the raw string.
    path = urlparse(image_url).path
    return path.rsplit(".", 1)[-1] if "." in path else "jpg"
