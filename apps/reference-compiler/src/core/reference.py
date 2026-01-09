import uuid

import httpx

from config import OUTPUT_DIRECTORY
from database import find_existing_reference, save_reference, update_reference
from handlers import get_handler
from models import ArtworkResponse

from .fetcher import download_image


async def process_url(url: str) -> list[ArtworkResponse]:
    handler = get_handler(url)
    if handler is None:
        raise ValueError("Unsupported URL")

    results = await handler.fetch_artwork(url)

    responses = []
    for result in results:
        existing = await find_existing_reference(url, result.media_type)

        if existing:
            reference_id = existing["id"]
            filename = existing["filename"]
        else:
            reference_id = str(uuid.uuid4())
            extension = result.image_url.rsplit(".", 1)[-1]
            filename = f"{reference_id}.{extension}"

        output_path = OUTPUT_DIRECTORY / filename

        try:
            await download_image(result.image_url, output_path)
        except httpx.HTTPError:
            continue

        if existing:
            await update_reference(reference_id, result.artist, result.track_name)
        else:
            await save_reference(
                reference_id, url, result.artist, result.track_name, result.media_type, filename
            )

        responses.append(ArtworkResponse(
            id=reference_id,
            filename=filename,
            artist=result.artist,
            track_name=result.track_name,
            media_type=result.media_type,
        ))

    return responses
