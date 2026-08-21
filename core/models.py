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
    OTHER = "other"

class Category(str, Enum):
    UNSORTED = "unsorted"
    PRO = "pro"
    PERSO = "perso"

class OriginalType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"

class Source(BaseModel):
    id:str = Field(default_factory=_uid)
    name:str
    url:HttpUrl
    type:SourceType=SourceType.OTHER

    # later...
    credibility_score: float | None = None
    source_summary:str | None = None

class Article(BaseModel):
    id:str = Field(default_factory=_uid)
    source_id:str
    url:HttpUrl | None = None
    title:str
    content:str
    fetched_at:datetime = Field(default_factory=_now)

    # later...
    category:Category=Category.UNSORTED
    n_tags:int = 0
    summary:str | None = None
    original_type:OriginalType | None = None

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
