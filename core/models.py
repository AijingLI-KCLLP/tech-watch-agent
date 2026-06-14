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

class Source(BaseModel):
    id:str = Field(default_factory=_uid)
    name:str
    url:HttpUrl
    type:SourceType=SourceType.OTHER

    # later...
    credibility_score: float | None = None
    why_interest:str | None = None

class Article(BaseModel):
    id:str = Field(default_factory=_uid)
    source_id:str
    url:HttpUrl
    title:str
    content:str
    fetched_at:datetime = Field(default_factory=_now)

    # later...
    category:Category=Category.UNSORTED
    tags:list[str] = Field(default_factory=list)
    summary:str | None = None

class Tag(BaseModel):
    id:str = Field(default_factory=_uid)
    name:str
    created_at:datetime = Field(default_factory=_now)

class Chunk(BaseModel):
    id:str = Field(default_factory=_uid)
    article_id:str
    text:str
    position:int