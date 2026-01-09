"""
Service for collecting reference material from URLs.
"""

import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from config import OUTPUT_DIRECTORY
from core.fetcher import download_image
from core.reference import process_url
from database import delete_reference, find_existing_reference, get_all_references, init_database, save_reference, update_reference
from handlers import get_handler
from models import ArtworkRequest, ArtworkResponse
from ui.templates import render_error_html, render_index, render_result_html


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


@app.delete("/reference/{reference_id}")
async def delete_reference_endpoint(reference_id: str):
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
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
async def index():
    references = await get_all_references()
    return render_index("", references)


@app.post("/", response_class=HTMLResponse)
async def submit_url(url: str = Form(...)):
    handler = get_handler(url)

    if handler is None:
        references = await get_all_references()
        return render_index(render_error_html("Unsupported URL."), references)

    try:
        results = await handler.fetch_artwork(url)
    except httpx.HTTPError as error:
        references = await get_all_references()
        return render_index(render_error_html(f"Failed to fetch page: {error}"), references)
    except ValueError:
        references = await get_all_references()
        return render_index(render_error_html("Nothing found."), references)

    saved_items = []
    for result in results:
        existing = await find_existing_reference(url, result.media_type)

        if existing:
            reference_id = existing["id"]
            filename = existing["filename"]
            action = "Updated"
        else:
            reference_id = str(uuid.uuid4())
            extension = result.image_url.rsplit(".", 1)[-1]
            filename = f"{reference_id}.{extension}"
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

    references = await get_all_references()

    if not saved_items:
        return render_index(render_error_html("Failed to download artwork."), references)

    return render_index(render_result_html(saved_items), references)


@app.post("/delete/{reference_id}", response_class=HTMLResponse)
async def delete_via_form(reference_id: str):
    references = await get_all_references()
    reference = next((r for r in references if r["id"] == reference_id), None)

    if reference:
        file_path = OUTPUT_DIRECTORY / reference["filename"]
        if file_path.exists():
            file_path.unlink()
        await delete_reference(reference_id)

    references = await get_all_references()
    return render_index("", references)
