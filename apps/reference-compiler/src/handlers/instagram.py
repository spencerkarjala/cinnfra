import html
import json
import re

from core.fetcher import fetch_page_content
from models import ArtworkResult, MediaType

from .base import BaseHandler

POST_PATTERN = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:[\w.]+/)?(?:p|reel|reels|tv)/([\w-]+)"
)

# Instagram serves post pages and embed pages as an empty app shell unless the
# request looks like a real browser; direct post pages are login-walled even
# then, but the embed page includes the full media data anonymously.
EMBED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
}

CONTEXT_JSON_MARKER = '"contextJSON":'
EMBED_IMAGE_PATTERN = re.compile(r'class="EmbeddedMediaImage"[^>]*?src="([^"]+)"')
EMBED_USERNAME_PATTERN = re.compile(r'UsernameText">([^<]+)')

CAPTION_MAX_LENGTH = 80


def _extract_shortcode_media(page_content: str) -> dict | None:
    marker_index = page_content.find(CONTEXT_JSON_MARKER)
    if marker_index == -1:
        return None

    # contextJSON's value is a JSON document serialized into a JSON string, so
    # it gets decoded twice.
    try:
        context_string, _ = json.JSONDecoder().raw_decode(
            page_content, marker_index + len(CONTEXT_JSON_MARKER)
        )
        context = json.loads(context_string)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(context, dict):
        return None
    gql_data = context.get("gql_data") or {}
    return gql_data.get("shortcode_media")


def _media_nodes(shortcode_media: dict) -> list[dict]:
    sidecar_edges = (shortcode_media.get("edge_sidecar_to_children") or {}).get("edges")
    if sidecar_edges:
        return [edge["node"] for edge in sidecar_edges if edge.get("node")]
    return [shortcode_media]


def _extract_caption(shortcode_media: dict) -> str:
    caption_edges = (shortcode_media.get("edge_media_to_caption") or {}).get("edges") or []
    if not caption_edges:
        return ""
    text = caption_edges[0].get("node", {}).get("text", "")
    if len(text) > CAPTION_MAX_LENGTH:
        return text[: CAPTION_MAX_LENGTH - 1] + "…"
    return text


class InstagramHandler(BaseHandler):

    @property
    def name(self) -> str:
        return "instagram"

    def can_handle(self, url: str) -> bool:
        return POST_PATTERN.match(url) is not None

    async def fetch_artwork(self, url: str) -> list[ArtworkResult]:
        post_match = POST_PATTERN.match(url)
        if not post_match:
            raise ValueError("Invalid URL format")

        shortcode = post_match.group(1)
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
        page_content = await fetch_page_content(embed_url, headers=EMBED_HEADERS)

        shortcode_media = _extract_shortcode_media(page_content)
        if shortcode_media:
            results = self._results_from_media_data(shortcode_media, shortcode)
        else:
            results = self._results_from_embed_html(page_content, shortcode)

        if not results:
            raise ValueError("No artwork found")

        return results

    def _results_from_media_data(
        self, shortcode_media: dict, shortcode: str
    ) -> list[ArtworkResult]:
        artist = (shortcode_media.get("owner") or {}).get("username", "")
        track_name = _extract_caption(shortcode_media) or shortcode

        results = []
        for index, node in enumerate(_media_nodes(shortcode_media)):
            if node.get("is_video") and node.get("video_url"):
                media_url = node["video_url"]
                base_media_type = MediaType.INSTAGRAM_POST_VIDEO
            elif node.get("display_url"):
                media_url = node["display_url"]
                base_media_type = MediaType.INSTAGRAM_POST_IMAGE
            else:
                continue

            # References are deduplicated by (url, media_type), so each
            # carousel position needs its own media type to survive a re-fetch.
            media_type = base_media_type if index == 0 else f"{base_media_type}_{index}"
            results.append(ArtworkResult(
                image_url=media_url,
                artist=artist,
                track_name=track_name,
                media_type=media_type,
            ))

        return results

    def _results_from_embed_html(
        self, page_content: str, shortcode: str
    ) -> list[ArtworkResult]:
        image_match = EMBED_IMAGE_PATTERN.search(page_content)
        if not image_match:
            return []

        username_match = EMBED_USERNAME_PATTERN.search(page_content)
        return [ArtworkResult(
            image_url=html.unescape(image_match.group(1)),
            artist=username_match.group(1) if username_match else "",
            track_name=shortcode,
            media_type=MediaType.INSTAGRAM_POST_IMAGE,
        )]
