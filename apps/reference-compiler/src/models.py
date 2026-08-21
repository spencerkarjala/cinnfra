from dataclasses import dataclass

from pydantic import BaseModel, Field, HttpUrl, field_validator


class MediaType:
    SOUNDCLOUD_TRACK_COVER = "SOUNDCLOUD_TRACK_COVER"
    SOUNDCLOUD_TRACK_WAVEFORM = "SOUNDCLOUD_TRACK_WAVEFORM"
    SOUNDCLOUD_PROFILE_AVATAR = "SOUNDCLOUD_PROFILE_AVATAR"
    SOUNDCLOUD_PROFILE_HEADER = "SOUNDCLOUD_PROFILE_HEADER"
    INSTAGRAM_POST_IMAGE = "INSTAGRAM_POST_IMAGE"
    INSTAGRAM_POST_VIDEO = "INSTAGRAM_POST_VIDEO"
    X_POST_IMAGE = "X_POST_IMAGE"
    X_POST_VIDEO = "X_POST_VIDEO"
    DIRECT_MEDIA_IMAGE = "DIRECT_MEDIA_IMAGE"
    DIRECT_MEDIA_VIDEO = "DIRECT_MEDIA_VIDEO"


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


class TagNameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=50)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank")
        return value


class TagCreate(TagNameRequest):
    pass


class TagUpdate(TagNameRequest):
    pass


class TagResponse(BaseModel):
    id: str
    display_name: str


class TagAssignment(BaseModel):
    tag_ids: list[str] = Field(default_factory=list)


class ReferenceNotesUpdate(BaseModel):
    notes: str


class ReferenceNotesResponse(BaseModel):
    reference_id: str
    notes: str
