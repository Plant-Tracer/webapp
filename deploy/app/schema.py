"""
schema.py - the types we store in DynamoDB
"""

from decimal import Decimal, ROUND_HALF_UP

from typing import Optional,Any,List
from pydantic import BaseModel,conint,condecimal,create_model,field_validator,ValidationError
from pydantic.fields import FieldInfo

class User(BaseModel):
    """DynamoDB users table"""
    user_id: str
    email: str
    full_name: str
    created: int
    enabled: conint(ge=0,le=1)
    demo: conint(ge=0,le=1)
    admin_for_courses: List[str]
    primary_course_id: str
    primary_course_name: str
    courses: List[str]

class UniqueEmail(BaseModel):
    """unique_emails table"""
    email: str

class ApiKey(BaseModel):
    """api_key model"""
    api_key: str
    user_id: str

class Course(BaseModel):
    """DynamoDB courses table"""
    course_id: str
    course_name: str
    course_key: str
    admins_for_course: List[str]
    max_enrollment: int

class CourseUser(BaseModel):
    """CourseUser tracks if a user is registered in the course"""
    user_id: str
    course_id: str

class Movie(BaseModel):
    """DynamoDB movies table"""
    movie_id: str
    title: str
    description: str
    created_at: int
    user_id: str
    course_id: str
    status: Optional[str] = None

    published: conint(ge=0, le=1)
    deleted: conint(ge=0, le=1)
    date_uploaded: Optional[int] = None
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

def fix_movie(movie):
    for tag in ['published','deleted','version']:
        if tag in movie:
            movie[tag] = int( movie[tag] )
    return movie

def fix_movies(movies):
    return [fix_movie(movie) for movie in movies]

class Trackpoint(BaseModel):
    """DynamoDB trackpoints table"""
    x: Decimal
    y: Decimal
    label: str
    frame_number: Optional[int] = None
    status: Optional[int] = None
    err: Optional[Decimal] = None

    @field_validator("x", "y", "err", mode="before")
    @classmethod
    def round_to_one_decimal(cls, v):
        if v is None:
            return v
        d = Decimal(str(v))  # string conversion avoids float issues
        return d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

class MovieFrame(BaseModel):
    """Each frame of each movie has a record"""
    movie_id: str
    frame_number: conint(ge=0)
    trackpoints: List[Trackpoint]

class LogEntry(BaseModel):
    """Logs"""
    log_id: str
    ipaddr: str
    user_id: str
    course_id: str
    time_t: conint(ge=0)

# Function to validate a single prop and value using the Movie schema
def validate_movie_field(prop: str, value: Any) -> tuple[str, Any]:
    field = Movie.model_fields.get(prop)
    if field is None:
        raise AttributeError(f"{prop} is not a valid field of Movie")

    field_type = field.annotation
    is_required = field.is_required

    # Dynamically create a Pydantic model with just this field
    TempModel = create_model("TempModel", **{prop: (field_type, ... if is_required else None)})

    try:
        validated = TempModel(**{prop: value})
        return getattr(validated, prop)
    except ValidationError as e:
        raise ValueError(f"Validation error for '{prop}': {e}") from e
