from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _uid() -> str:
    return uuid4().hex


class SourceType(str, Enum):
    BLOG = "blog"
    ARTICLE = "article"
    VIDEO = "video"
    PODCAST = "podcast"
    SOCIAL = "social"
    PERSONAL_NOTE = "personal_note"
    OTHER = "other"

class Category(str, Enum):
    INBOX = "inbox"
    AI_AUTOMATION = "ai_automation"
    TECH_CODE = "tech_code"
    PRODUCT_BUSINESS = "product_business"
    SCIENCE_RESEARCH = "science_research"
    DESIGN_CREATIVITY = "design_creativity"
    CULTURE_SOCIETY = "culture_society"
    LEARNING_LIFE = "learning_life"

class OriginalType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"


class DraftFormat(str, Enum):
    NOTE = "note"
    POST = "post"


class DraftStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"


class SourceVerificationStatus(str, Enum):
    VERIFIED = "verified"
    PLAUSIBLE = "plausible"
    UNVERIFIED = "unverified"
    MISMATCH = "mismatch"

class Source(BaseModel):
    id:str = Field(default_factory=_uid)
    name:str
    url:HttpUrl
    type:SourceType=SourceType.OTHER

    # later...
    credibility_score: float | None = Field(default=None, ge=0, le=1)
    credibility_reason: str | None = None
    source_summary:str | None = None

class Article(BaseModel):
    id:str = Field(default_factory=_uid)
    source_id: str | None = None
    url:HttpUrl | None = None
    title:str
    content:str
    fetched_at:datetime = Field(default_factory=_now)
    category:Category=Category.INBOX
    n_tags:int = 0
    summary:str | None = None
    original_type:OriginalType | None = None


class Draft(BaseModel):
    """An editable, unpublished piece generated from selected library content."""

    id: str = Field(default_factory=_uid)
    title: str
    intent: str
    format: DraftFormat
    platform: str
    language: str
    audience: str
    objective: str
    tone: str
    personal_angle: str
    source_summary: str
    generated_content: str
    content: str
    status: DraftStatus = DraftStatus.DRAFT
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class InputAsset(BaseModel):
    """The raw user input and its extraction provenance before Article normalization."""

    id: str = Field(default_factory=_uid)
    article_id: str | None = None
    original_type: OriginalType
    mime_type: str
    input_filename: str | None = None
    storage_path: str | None = None
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    raw_text: str | None = None
    extracted_text: str | None = None
    provided_source_url: HttpUrl | None = None
    source_verification_status: SourceVerificationStatus = (
        SourceVerificationStatus.UNVERIFIED
    )
    source_verification_reason: str | None = None
    source_verification_confidence: float | None = Field(default=None, ge=0, le=1)
    verified_source_id: str | None = None
    created_at: datetime = Field(default_factory=_now)

class Tag(BaseModel):
    id:str = Field(default_factory=_uid)
    name:str
    created_at:datetime = Field(default_factory=_now)

class ArticleTag(BaseModel):
    article_id:str
    tag_id:str

class Chunk(BaseModel):
    id:str = Field(default_factory=_uid)
    article_id:str
    text:str
    position:int
