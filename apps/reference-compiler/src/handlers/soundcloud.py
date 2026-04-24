import re

from core.fetcher import fetch_page_content
from models import ArtworkResult, MediaType

from .base import BaseHandler

TRACK_PATTERN = re.compile(r"^https?://soundcloud\.com/([\w-]+)/([\w-]+)/?$")
PROFILE_PATTERN = re.compile(r"^https?://soundcloud\.com/([\w-]+)/?$")
ARTWORK_PATTERN = re.compile(
    r"(https://i1\.sndcdn\.com/artworks-[^\"']+?)-(\w+)\.(jpg|png|jpeg)"
)
WAVEFORM_PATTERN = re.compile(
    r"(https://i1\.sndcdn\.com/visuals-[a-zA-Z0-9]{16}-[^\"']+?)-(\w+)\.(jpg|png|jpeg)"
)
AVATAR_PATTERN = re.compile(
    r"(https://i1\.sndcdn\.com/avatars-[^\"']+?)-(\w+)\.(jpg|png|jpeg)"
)
PROFILE_HEADER_PATTERN = re.compile(
    r"(https://i1\.sndcdn\.com/visuals-[^\"']+?)-(\w+)\.(jpg|png|jpeg)"
)
OG_TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]+)"')
TITLE_ARTIST_PATTERN = re.compile(r'<title>Stream .+ by (.+?) \| Listen')


class SoundCloudHandler(BaseHandler):

    @property
    def name(self) -> str:
        return "soundcloud"

    def can_handle(self, url: str) -> bool:
        return TRACK_PATTERN.match(url) is not None or PROFILE_PATTERN.match(url) is not None

    async def fetch_artwork(self, url: str) -> list[ArtworkResult]:
        track_match = TRACK_PATTERN.match(url)
        profile_match = PROFILE_PATTERN.match(url)

        if not track_match and not profile_match:
            raise ValueError("Invalid URL format")

        page_content = await fetch_page_content(url)
        results = []

        if track_match:
            og_title_match = OG_TITLE_PATTERN.search(page_content)
            track_name = og_title_match.group(1) if og_title_match else track_match.group(2)

            artist_match = TITLE_ARTIST_PATTERN.search(page_content)
            artist = artist_match.group(1) if artist_match else track_match.group(1)

            artwork_match = ARTWORK_PATTERN.search(page_content)
            if artwork_match:
                base_url = artwork_match.group(1)
                extension = artwork_match.group(3)
                results.append(ArtworkResult(
                    image_url=f"{base_url}-original.{extension}",
                    artist=artist,
                    track_name=track_name,
                    media_type=MediaType.SOUNDCLOUD_TRACK_COVER,
                ))

            waveform_match = WAVEFORM_PATTERN.search(page_content)
            if waveform_match:
                base_url = waveform_match.group(1)
                extension = waveform_match.group(3)
                results.append(ArtworkResult(
                    image_url=f"{base_url}-original.{extension}",
                    artist=artist,
                    track_name=track_name,
                    media_type=MediaType.SOUNDCLOUD_TRACK_WAVEFORM,
                ))

        elif profile_match:
            artist = profile_match.group(1)

            og_title_match = OG_TITLE_PATTERN.search(page_content)
            display_name = og_title_match.group(1) if og_title_match else artist

            avatar_match = AVATAR_PATTERN.search(page_content)
            if avatar_match:
                base_url = avatar_match.group(1)
                extension = avatar_match.group(3)
                results.append(ArtworkResult(
                    image_url=f"{base_url}-original.{extension}",
                    artist=display_name,
                    track_name="",
                    media_type=MediaType.SOUNDCLOUD_PROFILE_AVATAR,
                ))

            header_match = PROFILE_HEADER_PATTERN.search(page_content)
            if header_match:
                base_url = header_match.group(1)
                extension = header_match.group(3)
                results.append(ArtworkResult(
                    image_url=f"{base_url}-original.{extension}",
                    artist=display_name,
                    track_name="",
                    media_type=MediaType.SOUNDCLOUD_PROFILE_HEADER,
                ))

        if not results:
            raise ValueError("No artwork found")

        return results
