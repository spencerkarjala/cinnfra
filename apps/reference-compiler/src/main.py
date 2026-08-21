"""
Service for collecting reference material from URLs.
"""

import sqlite3
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from config import OUTPUT_DIRECTORY
from core.fetcher import download_image, image_extension
from core.reference import process_url
from database import (
    create_tag,
    delete_reference,
    delete_tag,
    find_existing_reference,
    get_all_references,
    get_all_tags,
    get_reference,
    init_database,
    save_reference,
    set_reference_tags,
    update_reference,
    update_reference_notes,
    update_tag,
)
from handlers import get_handler
from models import (
    ArtworkRequest,
    ArtworkResponse,
    ReferenceNotesResponse,
    ReferenceNotesUpdate,
    TagAssignment,
    TagCreate,
    TagResponse,
    TagUpdate,
)
from ui.templates import render_error_html, render_index, render_notice_html


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


async def render_page(result: str = "") -> str:
    references = await get_all_references()
    tags = await get_all_tags()
    return render_index(result, references, tags)


def redirect_to_index(message: str | None = None, *, error: bool = False) -> RedirectResponse:
    location = "/"
    if message:
        parameter = "error" if error else "notice"
        location = f"/?{urlencode({parameter: message})}"
    return RedirectResponse(location, status_code=303)


@app.post("/artwork", response_model=list[ArtworkResponse])
async def fetch_artwork(request: ArtworkRequest):
    url = str(request.url)

    try:
        responses = await process_url(url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Failed to fetch page: {error}")

    if not responses:
        raise HTTPException(status_code=502, detail="Failed to download any artwork")

    return responses


@app.get("/artwork/{filename}")
async def get_artwork(filename: str):
    file_path = OUTPUT_DIRECTORY / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(file_path)


@app.get("/tags", response_model=list[TagResponse])
async def list_tags():
    return await get_all_tags()


@app.post("/tags", response_model=TagResponse, status_code=201)
async def create_tag_endpoint(request: TagCreate):
    try:
        return await create_tag(str(uuid.uuid4()), request.display_name)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="A tag with that display name already exists"
        ) from None


@app.patch("/tags/{tag_id}", response_model=TagResponse)
async def update_tag_endpoint(tag_id: str, request: TagUpdate):
    try:
        tag = await update_tag(tag_id, request.display_name)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="A tag with that display name already exists"
        ) from None

    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@app.delete("/tags/{tag_id}")
async def delete_tag_endpoint(tag_id: str):
    if not await delete_tag(tag_id):
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"deleted": tag_id}


@app.put("/reference/{reference_id}/tags", response_model=list[TagResponse])
async def assign_reference_tags(reference_id: str, request: TagAssignment):
    try:
        tags = await set_reference_tags(reference_id, request.tag_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if tags is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    return tags


@app.patch(
    "/reference/{reference_id}/notes", response_model=ReferenceNotesResponse
)
async def update_reference_notes_endpoint(
    reference_id: str, request: ReferenceNotesUpdate
):
    if not await update_reference_notes(reference_id, request.notes):
        raise HTTPException(status_code=404, detail="Reference not found")
    return ReferenceNotesResponse(reference_id=reference_id, notes=request.notes)


@app.delete("/reference/{reference_id}")
async def delete_reference_endpoint(reference_id: str):
    reference = await get_reference(reference_id)

    if reference is None:
        raise HTTPException(status_code=404, detail="Not found")

    file_path = OUTPUT_DIRECTORY / reference["filename"]
    if file_path.exists():
        file_path.unlink()

    await delete_reference(reference_id)
    return {"deleted": reference_id}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
async def index(notice: str | None = None, error: str | None = None):
    if error:
        result = render_error_html(error)
    elif notice:
        result = render_notice_html(notice)
    else:
        result = ""
    return await render_page(result)


@app.post("/")
async def submit_url(url: str = Form(...)):
    handler = get_handler(url)

    if handler is None:
        return redirect_to_index("Unsupported URL.", error=True)

    try:
        results = await handler.fetch_artwork(url)
    except httpx.HTTPError as error:
        return redirect_to_index(f"Failed to fetch page: {error}", error=True)
    except ValueError:
        return redirect_to_index("Nothing found.", error=True)

    saved_items = []
    for result in results:
        existing = await find_existing_reference(url, result.media_type)

        if existing:
            reference_id = existing["id"]
            filename = existing["filename"]
            action = "Updated"
        else:
            reference_id = str(uuid.uuid4())
            filename = f"{reference_id}.{image_extension(result.image_url)}"
            action = "Saved"

        output_path = OUTPUT_DIRECTORY / filename

        try:
            await download_image(result.image_url, output_path)
        except httpx.HTTPError:
            continue

        if existing:
            await update_reference(reference_id, result.artist, result.track_name)
        else:
            await save_reference(reference_id, url, result.artist, result.track_name, result.media_type, filename)

        saved_items.append((action, result, filename))

    if not saved_items:
        return redirect_to_index("Failed to download artwork.", error=True)

    saved_count = sum(action == "Saved" for action, _, _ in saved_items)
    updated_count = len(saved_items) - saved_count
    summaries = []
    if saved_count:
        summaries.append(f"Saved {saved_count} reference{'s' if saved_count != 1 else ''}")
    if updated_count:
        summaries.append(f"Updated {updated_count} reference{'s' if updated_count != 1 else ''}")
    return redirect_to_index(" and ".join(summaries) + ".")


@app.post("/delete/{reference_id}")
async def delete_via_form(reference_id: str):
    reference = await get_reference(reference_id)

    if reference:
        file_path = OUTPUT_DIRECTORY / reference["filename"]
        if file_path.exists():
            file_path.unlink()
        await delete_reference(reference_id)

    return redirect_to_index()
