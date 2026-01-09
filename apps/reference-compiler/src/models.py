from dataclasses import dataclass

from pydantic import BaseModel, HttpUrl


class MediaType:
    SOUNDCLOUD_TRACK_COVER = "SOUNDCLOUD_TRACK_COVER"
    SOUNDCLOUD_TRACK_WAVEFORM = "SOUNDCLOUD_TRACK_WAVEFORM"


@dataclass
class ArtworkResult:
    image_url: str
    artist: str
    track_name: str
    media_type: str


class ArtworkRequest(BaseModel):
    url: HttpUrl


class ArtworkResponse(BaseModel):
    id: str
    filename: str
    artist: str
    track_name: str
    media_type: str
