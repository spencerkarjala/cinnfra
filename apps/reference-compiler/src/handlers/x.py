import json
import re
from urllib.parse import urlencode

from core.fetcher import fetch_page_content
from models import ArtworkResult, MediaType

from .base import BaseHandler


STATUS_PATTERN = re.compile(
    r"^https?://(?:(?:www|mobile)\.)?(?:x\.com|twitter\.com)/"
    r"(?:[^/?#]+/status|i/web/status)/(\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)
SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
TITLE_MAX_LENGTH = 80


def _post_title(post: dict, post_id: str) -> str:
    text = post.get("text") or ""
    display_range = post.get("display_text_range")
    if (
        isinstance(display_range, list)
        and len(display_range) == 2
        and all(isinstance(offset, int) for offset in display_range)
    ):
        text = text[display_range[0] : display_range[1]]

    text = " ".join(text.split())
    if len(text) > TITLE_MAX_LENGTH:
        text = text[: TITLE_MAX_LENGTH - 1] + "…"
    return text or post_id


def _best_video_url(media: dict) -> str | None:
    variants = (media.get("video_info") or {}).get("variants") or []
    mp4_variants = [
        variant
        for variant in variants
        if variant.get("content_type") == "video/mp4" and variant.get("url")
    ]
    if not mp4_variants:
        return None
    return max(mp4_variants, key=lambda variant: variant.get("bitrate") or 0)["url"]


class XHandler(BaseHandler):

    @property
    def name(self) -> str:
        return "x"

    def can_handle(self, url: str) -> bool:
        return STATUS_PATTERN.match(url) is not None

    async def fetch_artwork(self, url: str) -> list[ArtworkResult]:
        status_match = STATUS_PATTERN.match(url)
        if not status_match:
            raise ValueError("Invalid X post URL")

        post_id = status_match.group(1)
        query = urlencode({"id": post_id, "lang": "en", "token": "1"})
        page_content = await fetch_page_content(f"{SYNDICATION_URL}?{query}")
        try:
            post = json.loads(page_content)
        except json.JSONDecodeError as error:
            raise ValueError("Invalid response from X") from error

        if not isinstance(post, dict) or not post.get("id_str"):
            raise ValueError("X post was not found")

        user = post.get("user") or {}
        artist = user.get("screen_name") or user.get("name") or ""
        title = _post_title(post, post_id)
        results = []

        for index, media in enumerate(post.get("mediaDetails") or []):
            video_url = _best_video_url(media)
            if video_url:
                media_url = video_url
                base_media_type = MediaType.X_POST_VIDEO
            elif media.get("media_url_https"):
                media_url = media["media_url_https"]
                base_media_type = MediaType.X_POST_IMAGE
            else:
                continue

            # References are deduplicated by (url, media_type), so each media
            # position needs its own type when a post contains several items.
            media_type = base_media_type if index == 0 else f"{base_media_type}_{index}"
            results.append(
                ArtworkResult(
                    image_url=media_url,
                    artist=artist,
                    track_name=title,
                    media_type=media_type,
                )
            )

        if not results:
            raise ValueError("No media found in X post")
        return results
