"""Typed news contracts; article clocks are distinct and always timezone-aware."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, field_validator


def utc(value):
    if value is None:
        return None
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timestamp timezone required")
    return d.astimezone(timezone.utc).isoformat()


class ArticleInput(BaseModel):
    provider_article_id: str = Field(min_length=1, max_length=300)
    url: str = Field(max_length=2000)
    publisher: str = Field(min_length=1, max_length=300)
    headline: str = Field(min_length=1, max_length=2000)
    text: str = Field(default="", max_length=80000)
    language: str = "en"
    published_at: str
    updated_at: str | None = None
    provider_first_seen_at: str | None = None
    availability_evidence: str | None = Field(default=None, max_length=2000)
    event_at: str | None = None
    content_scope: Literal["headline", "snippet", "full_text"] = "snippet"
    rights: str = Field(min_length=1, max_length=2000)
    event_id: str | None = Field(default=None, max_length=300)

    @field_validator("published_at", "updated_at", "provider_first_seen_at", "event_at")
    @classmethod
    def timestamps(cls, value):
        return utc(value)

    @field_validator("url")
    @classmethod
    def public_url(cls, value):
        from urllib.parse import urlparse
        u = urlparse(value)
        if u.scheme not in {"https", "http"} or not u.hostname or u.username or u.password:
            raise ValueError("Article URL must be an HTTP(S) link without credentials")
        return value


class ImportRequest(BaseModel):
    provider: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$", default="local")
    articles: list[ArticleInput] = Field(min_length=1, max_length=1000)


class PacketRequest(BaseModel):
    symbol: str = "BTCUSDT"
    origin: str
    lookback_days: int = Field(default=7, ge=1, le=365)
    policy: Literal["strict", "exploratory"] = "strict"


class ClassifyRequest(BaseModel):
    packet_id: str
    classifier: Literal["keywords", "jev", "openai"] = "keywords"
    budget_usd: float = Field(default=0, ge=0, le=100)
    max_articles: int = Field(default=100, ge=1, le=1000)


class LabelRequest(BaseModel):
    article_id: str
    symbol: str = "BTCUSDT"
    annotator: str = Field(min_length=1, max_length=200)
    relevance: Literal["relevant", "irrelevant", "unknown"]
    category: str
    framing: Literal["positive", "negative", "mixed", "neutral", "unknown"]
    note: str = Field(default="", max_length=2000)


class ForecastExperimentRequest(BaseModel):
    symbol: str = "BTCUSDT"
    policy: Literal["strict", "exploratory"] = "strict"
    lookback_days: int = Field(default=30, ge=30, le=180)
    minimum_origins: int = Field(default=30, ge=30, le=365)
    evidence_lookback_days: int = Field(default=7, ge=1, le=30)

