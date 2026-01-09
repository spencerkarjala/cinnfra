from pathlib import Path

import httpx


async def fetch_page_content(url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


async def download_image(image_url: str, output_path: Path) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url, follow_redirects=True)
        response.raise_for_status()
        output_path.write_bytes(response.content)
