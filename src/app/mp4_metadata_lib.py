"""
Shared logic for viewing and setting research-attribution comment metadata in MP4/MOV files.
Used by the etc/mp4_metadata.py CLI and by lambda-resize when processing uploaded videos.
Uses mutagen only; no external OS tools.
"""
import io
from typing import Optional

from PIL import Image
from mutagen.mp4 import MP4, MP4Tags

COMMENT_ATOM = "\xa9cmt"

RESEARCH_PROHIBITED = "research use prohibited"
RESEARCH_ANONYMOUS = "research use allowed (no credit required)"


def research_credit(name: str) -> str:
    """Return the comment string for research use with credit to name."""
    return f"research use allowed; credit {name}"


def build_comment(
    research_use: int,
    credit_by_name: int,
    attribution_name: Optional[str] = None,
) -> str:
    """Build the research-attribution comment string from DB fields (same logic as CLI).
    research_use: 0 or 1; credit_by_name: 0 or 1; attribution_name: name when credit_by_name==1.
    """
    if research_use == 0:
        return RESEARCH_PROHIBITED
    if credit_by_name != 1 or not attribution_name:
        return RESEARCH_ANONYMOUS
    return research_credit(attribution_name)


def get_comment(path: str) -> str | None:
    """Read the comment tag from an MP4/MOV file. Returns None if missing or on error."""
    try:
        mp4 = MP4(path)
        if mp4.tags is None:
            return None
        values = mp4.tags.get(COMMENT_ATOM, [])
        if not values:
            return None
        part = values[0]
        return part if isinstance(part, str) else str(part)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def set_comment(path: str, comment: str) -> None:
    """Set the comment tag and save the file."""
    mp4 = MP4(path)
    if mp4.tags is None:
        mp4.add_tags()
    assert isinstance(mp4.tags, MP4Tags)
    mp4.tags[COMMENT_ATOM] = [comment]
    mp4.save()


def add_comment_to_jpeg(jpeg_bytes: bytes, comment: str, quality: int = 60) -> bytes:
    """Add a JPEG comment (COM segment) to JPEG bytes. Returns new bytes.
    Used so every frame in the tracking zip carries the research-attribution metadata.
    """
    img = Image.open(io.BytesIO(jpeg_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.info["comment"] = comment.encode("utf-8") if isinstance(comment, str) else comment
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()
