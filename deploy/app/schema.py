"""
schema.py - the types we store in DynamoDB
"""

from decimal import Decimal, ROUND_HALF_UP

from typing import Literal,Optional,Any
from pydantic import BaseModel,conint,AnyUrl,condecimal,create_model,field_validator,ValidationError

class Movie(BaseModel):
    movie_id: str
    title: str
    description: str
    created_at: conint(gt=0)
    user_id: str
    course_id: str
    status: str

    published: conint(ge=0, le=1)
    deleted: conint(ge=0, le=1)
    date_uploaded: Optional[conint(gt=0)] = None
    orig_movie: Optional[str] = None
    fps:  Optional[condecimal(max_digits=4, decimal_places=2)] = None
    width: Optional[conint(ge=0, le=10000)] = None
    height: Optional[conint(ge=0, le=10000)] = None

    total_frames: Optional[conint(ge=0)] = None
    total_bytes: Optional[conint(ge=0)] = None

    movie_data_urn: Optional[str] = None
    movie_zipfile_urn: Optional[str] = None

    last_frame_tracked: Optional[conint(ge=0)] = None

    version: Optional[conint(ge=0)] = None

class Trackpoint(BaseModel):
    x: Decimal
    y: Decimal
    label: str
    frame_number: Optional[int] = None
    status: Optional[int] = None
    err: Optional[Decimal] = None

    @field_validator("x", "y", "err", mode="before")
    def round_to_one_decimal(cls, v):
        if v is None:
            return v
        d = Decimal(str(v))  # string conversion avoids float issues
        return d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Function to validate a single prop and value using the Movie schema
def validate_movie_field(prop: str, value: Any) -> tuple[str, Any]:
    if prop not in Movie.model_fields:
        raise AttributeError(f"{prop} is not a valid field of Movie")

    field_type = Movie.model_fields[prop].annotation
    is_required = Movie.model_fields[prop].is_required

    # Dynamically create a Pydantic model with just this field
    TempModel = create_model("TempModel", **{prop: (field_type, ... if is_required else None)})

    try:
        validated = TempModel(**{prop: value})
        return getattr(validated, prop)
    except ValidationError as e:
        raise ValueError(f"Validation error for '{prop}': {e}")
