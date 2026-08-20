from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from models import ArtworkResult, MediaType

from .base import BaseHandler


IMAGE_EXTENSIONS = {"avif", "bmp", "gif", "jpeg", "jpg", "png", "tif", "tiff", "webp"}
VIDEO_EXTENSIONS = {"m4v", "mov", "mp4", "webm"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


class DirectMediaHandler(BaseHandler):

    @property
    def name(self) -> str:
        return "direct-media"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        extension = PurePosixPath(parsed.path).suffix.removeprefix(".").lower()
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and extension in MEDIA_EXTENSIONS

    async def fetch_artwork(self, url: str) -> list[ArtworkResult]:
        if not self.can_handle(url):
            raise ValueError("Invalid direct media URL")

        parsed = urlparse(url)
        filename = unquote(PurePosixPath(parsed.path).name)
        extension = PurePosixPath(parsed.path).suffix.removeprefix(".").lower()
        media_type = (
            MediaType.DIRECT_MEDIA_VIDEO
            if extension in VIDEO_EXTENSIONS
            else MediaType.DIRECT_MEDIA_IMAGE
        )

        return [ArtworkResult(
            image_url=url,
            artist=parsed.netloc,
            track_name=filename,
            media_type=media_type,
        )]
