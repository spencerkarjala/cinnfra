"""
Service for collecting reference material from URLs.
"""

import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine

import aiosqlite
import httpx
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, HttpUrl


OUTPUT_DIRECTORY = Path(os.environ.get("OUTPUT_DIR", "/output"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "/output/references.db"))

SOUNDCLOUD_TRACK_PATTERN = re.compile(r"^https?://soundcloud\.com/([\w-]+)/([\w-]+)/?$")
SOUNDCLOUD_ARTWORK_PATTERN = re.compile(
    r"(https://i1\.sndcdn\.com/artworks-[^\"']+?)-(\w+)\.(jpg|png|jpeg)"
)


class MediaType:
    SOUNDCLOUD_TRACK_COVER = "SOUNDCLOUD_TRACK_COVER"
    SOUNDCLOUD_TRACK_WAVEFORM = "SOUNDCLOUD_TRACK_WAVEFORM"


@dataclass
class ArtworkResult:
    image_url: str
    artist: str
    track_name: str
    media_type: str


ArtworkHandler = Callable[[str], Coroutine[None, None, ArtworkResult]]


class ArtworkRequest(BaseModel):
    url: HttpUrl


class ArtworkResponse(BaseModel):
    id: str
    filename: str
    artist: str
    track_name: str
    media_type: str


async def init_database():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS references (
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
            INSERT INTO references (id, url, artist, track_name, media_type, filename, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (reference_id, url, artist, track_name, media_type, filename, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def get_all_references() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM references ORDER BY fetched_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def delete_reference(reference_id: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM references WHERE id = ?", (reference_id,))
        await db.commit()
        return cursor.rowcount > 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    await init_database()
    yield


app = FastAPI(
    title="Reference Compiler",
    description="Collects reference material from URLs",
    lifespan=lifespan,
)


async def fetch_page_content(url: str) -> str:
    """Fetches HTML content from a URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


async def download_image(image_url: str, output_path: Path) -> None:
    """Downloads an image from a URL to the specified path."""
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url, follow_redirects=True)
        response.raise_for_status()
        output_path.write_bytes(response.content)


async def fetch_soundcloud_artwork(url: str) -> ArtworkResult:
    """Fetches artwork and metadata from a SoundCloud track page."""
    match = SOUNDCLOUD_TRACK_PATTERN.match(url)
    if not match:
        raise ValueError("Invalid URL format")

    artist = match.group(1)
    track_name = match.group(2)

    page_content = await fetch_page_content(url)
    artwork_match = SOUNDCLOUD_ARTWORK_PATTERN.search(page_content)
    if not artwork_match:
        raise ValueError("No artwork found")

    base_url = artwork_match.group(1)
    extension = artwork_match.group(3)
    image_url = f"{base_url}-original.{extension}"

    return ArtworkResult(
        image_url=image_url,
        artist=artist,
        track_name=track_name,
        media_type=MediaType.SOUNDCLOUD_TRACK_COVER,
    )


def get_artwork_handler(url: str) -> ArtworkHandler | None:
    """Returns the appropriate handler for a URL, or None if unsupported."""
    if SOUNDCLOUD_TRACK_PATTERN.match(url):
        return fetch_soundcloud_artwork
    return None


@app.post("/artwork", response_model=ArtworkResponse)
async def fetch_artwork(request: ArtworkRequest):
    """Fetches artwork from a URL and saves it to the database."""
    url = str(request.url)
    handler = get_artwork_handler(url)

    if handler is None:
        raise HTTPException(status_code=400, detail="Unsupported URL")

    try:
        result = await handler(url)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Failed to fetch page: {error}")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))

    reference_id = str(uuid.uuid4())
    extension = result.image_url.rsplit(".", 1)[-1]
    filename = f"{reference_id}.{extension}"
    output_path = OUTPUT_DIRECTORY / filename

    try:
        await download_image(result.image_url, output_path)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Failed to download: {error}")

    await save_reference(reference_id, url, result.artist, result.track_name, result.media_type, filename)

    return ArtworkResponse(
        id=reference_id,
        filename=filename,
        artist=result.artist,
        track_name=result.track_name,
        media_type=result.media_type,
    )


@app.get("/artwork/{filename}")
async def get_artwork(filename: str):
    """Serves a previously downloaded artwork file."""
    file_path = OUTPUT_DIRECTORY / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(file_path)


@app.delete("/reference/{reference_id}")
async def delete_reference_endpoint(reference_id: str):
    """Deletes a reference and its artwork file."""
    references = await get_all_references()
    reference = next((r for r in references if r["id"] == reference_id), None)

    if reference is None:
        raise HTTPException(status_code=404, detail="Not found")

    file_path = OUTPUT_DIRECTORY / reference["filename"]
    if file_path.exists():
        file_path.unlink()

    await delete_reference(reference_id)
    return {"deleted": reference_id}


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes probes."""
    return {"status": "healthy"}


INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Reference Compiler</title>
    <style>
        body {{
            font-family: system-ui, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1a1a1a;
            color: #e0e0e0;
        }}
        h1, h2 {{ color: #fff; }}
        form {{ margin: 20px 0; }}
        input[type="url"] {{
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 1px solid #444;
            border-radius: 4px;
            background: #2a2a2a;
            color: #e0e0e0;
            box-sizing: border-box;
        }}
        button {{
            margin-top: 10px;
            padding: 12px 24px;
            font-size: 16px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}
        button:hover {{ background: #0055aa; }}
        .delete-btn {{
            background: #cc3333;
            padding: 6px 12px;
            font-size: 14px;
            margin: 0;
        }}
        .delete-btn:hover {{ background: #aa2222; }}
        .result, .reference {{
            margin-top: 20px;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 4px;
        }}
        .result img, .reference img {{
            max-width: 200px;
            margin-top: 10px;
            border-radius: 4px;
        }}
        .reference {{
            display: flex;
            gap: 15px;
            align-items: flex-start;
        }}
        .reference-info {{
            flex: 1;
        }}
        .reference-info p {{
            margin: 5px 0;
        }}
        .error {{ color: #ff6b6b; }}
        a {{ color: #66b3ff; }}
        hr {{ border-color: #444; margin: 30px 0; }}
        .media-type {{ color: #888; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>Reference Compiler</h1>
    <form method="post" action="/">
        <input type="url" name="url" placeholder="https://..." required>
        <button type="submit">Fetch</button>
    </form>
    {result}
    <hr>
    <h2>Saved References</h2>
    {references}
</body>
</html>
"""


def render_references_html(references: list[dict]) -> str:
    if not references:
        return "<p>No references saved yet.</p>"

    html_parts = []
    for ref in references:
        html_parts.append(f'''
        <div class="reference">
            <img src="/artwork/{ref["filename"]}" alt="Artwork">
            <div class="reference-info">
                <p><strong>{ref["artist"]}</strong> - {ref["track_name"]}</p>
                <p class="media-type">{ref["media_type"]}</p>
                <p><a href="{ref["url"]}" target="_blank">Source</a></p>
                <form method="post" action="/delete/{ref["id"]}" style="margin:0">
                    <button type="submit" class="delete-btn">Delete</button>
                </form>
            </div>
        </div>
        ''')
    return "".join(html_parts)


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serves the main HTML form."""
    references = await get_all_references()
    return INDEX_HTML.format(result="", references=render_references_html(references))


@app.post("/", response_class=HTMLResponse)
async def submit_url(url: str = Form(...)):
    """Handles form submission and displays the fetched artwork."""
    handler = get_artwork_handler(url)

    if handler is None:
        references = await get_all_references()
        error_html = '<div class="result error">Unsupported URL.</div>'
        return INDEX_HTML.format(result=error_html, references=render_references_html(references))

    try:
        result = await handler(url)
    except httpx.HTTPError as error:
        references = await get_all_references()
        error_html = f'<div class="result error">Failed to fetch page: {error}</div>'
        return INDEX_HTML.format(result=error_html, references=render_references_html(references))
    except ValueError:
        references = await get_all_references()
        error_html = '<div class="result error">Nothing found.</div>'
        return INDEX_HTML.format(result=error_html, references=render_references_html(references))

    reference_id = str(uuid.uuid4())
    extension = result.image_url.rsplit(".", 1)[-1]
    filename = f"{reference_id}.{extension}"
    output_path = OUTPUT_DIRECTORY / filename

    try:
        await download_image(result.image_url, output_path)
    except httpx.HTTPError as error:
        references = await get_all_references()
        error_html = f'<div class="result error">Failed to download: {error}</div>'
        return INDEX_HTML.format(result=error_html, references=render_references_html(references))

    await save_reference(reference_id, url, result.artist, result.track_name, result.media_type, filename)

    references = await get_all_references()
    result_html = f'''
    <div class="result">
        <p>Saved: <strong>{result.artist}</strong> - {result.track_name}</p>
        <img src="/artwork/{filename}" alt="Artwork">
    </div>
    '''
    return INDEX_HTML.format(result=result_html, references=render_references_html(references))


@app.post("/delete/{reference_id}", response_class=HTMLResponse)
async def delete_via_form(reference_id: str):
    """Handles delete form submission."""
    references = await get_all_references()
    reference = next((r for r in references if r["id"] == reference_id), None)

    if reference:
        file_path = OUTPUT_DIRECTORY / reference["filename"]
        if file_path.exists():
            file_path.unlink()
        await delete_reference(reference_id)

    references = await get_all_references()
    return INDEX_HTML.format(result="", references=render_references_html(references))
