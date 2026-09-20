"""Export freshness, independent of whether saved positions need retracking."""

import hashlib
from pydantic import BaseModel


class MovieRenderInputs(BaseModel):
    """Movie fields that determine the traced MP4, including annotation revision.

    Internal analysis_mp4 names remain compatible; that derivative is the
    untraced MP4. Its geometry is represented by frame_height_px here.
    """

    movie_data_urn: str | None = None
    render_revision: str | None = None
    rotation: int = 0
    frame_height_px: int | None = None
    trackpoint_origin: str | None = None
    total_frames: int | None = None
    trim_start_frame: int | None = None
    trim_end_frame: int | None = None
    fpm: str | None = None
    research_use: int | None = None
    credit_by_name: int | None = None
    attribution_name: str | None = None

    def key(self):
        """Versioned fingerprint; legacy exports without this key rebuild once."""
        return hashlib.sha256(('1:' + self.model_dump_json()).encode()).hexdigest()


def render_key(movie):
    """Return the fingerprint without reading any per-frame DynamoDB records."""
    return MovieRenderInputs.model_validate(movie).key()


def render_input_values(movie):
    """Raw values for conditional publication, preserving missing attributes."""
    return {field: movie.get(field) for field in MovieRenderInputs.model_fields.keys()}
