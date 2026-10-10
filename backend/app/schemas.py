import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Ticker = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")]


def normalize_ticker(value: str) -> str:
    value = value.strip().lstrip("$").upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", value):
        raise ValueError("Invalid ticker")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchInput(StrictModel):
    ticker: Ticker
    company_name: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4000)

    @field_validator("ticker", mode="before")
    @classmethod
    def ticker_input(cls, v: str) -> str:
        return normalize_ticker(v)


class ThesisInput(StrictModel):
    ticker: Ticker
    thesis: str = Field(min_length=1, max_length=12000)


class PreferenceInput(StrictModel):
    risk_tolerance: Literal["conservative", "balanced", "aggressive"]
    investment_horizon: Literal["short", "medium", "long"]


class TrustInput(StrictModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{1,15}$")
    rating: Literal["trusted", "unrated", "caution"]
    reason: str = Field(min_length=1, max_length=2000)


class AccountInput(StrictModel):
    username: str = Field(pattern=r"^@?[A-Za-z0-9_]{1,15}$")


class ResearchInput(StrictModel):
    question: str = Field(min_length=2, max_length=6000)
    ticker: Ticker | None = None
    post_id: str | None = Field(default=None, pattern=r"^\d{1,30}$")
    request_key: str | None = Field(default=None, min_length=8, max_length=120)


class ChatInput(StrictModel):
    content: str = Field(min_length=1, max_length=6000)
    request_key: str | None = Field(default=None, min_length=8, max_length=120)


class DecisionInput(StrictModel):
    args: dict | None = None
    reason: str = Field(default="", max_length=2000)


class AppPreferences(StrictModel):
    sync_enabled: bool = True
    sync_interval_minutes: int = Field(default=60, ge=30, le=1440)
    daily_brief_enabled: bool = True
    daily_brief_hour: int = Field(default=8, ge=0, le=23)
    timezone: str = "Asia/Shanghai"
    auto_research_enabled: bool = False
    auto_research_max_per_day: int = Field(default=2, ge=0, le=10)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown IANA timezone") from None
        return value


class EvidenceDraft(StrictModel):
    source_id: str = Field(description="Exact source_id returned by a tool; never invent")
    stance: Literal["support", "contradict", "context"]
    quote: str = Field(
        min_length=1, max_length=1800, description="Exact verbatim passage present in this source excerpt"
    )
    rationale: str = Field(max_length=1500)


class ClaimDraft(StrictModel):
    text: str = Field(max_length=2000, description="One atomic claim only")
    kind: Literal["fact", "prediction", "opinion", "inference"]
    tickers: list[str] = Field(default_factory=list, max_length=8)
    metric: str | None = None
    period: str | None = None
    unit: str | None = None
    comparison: str | None = None
    as_of: str | None = None
    assessment: Literal[
        "supported",
        "partially_supported",
        "contradicted",
        "conflicting",
        "insufficient_evidence",
        "not_verifiable",
    ]
    explanation: str = Field(max_length=2000)
    evidence: list[EvidenceDraft] = Field(default_factory=list, max_length=8)


class FactorDraft(StrictModel):
    text: str = Field(max_length=1500)
    source_ids: list[str] = Field(default_factory=list, max_length=8)


class ReportDraft(StrictModel):
    title: str = Field(max_length=180)
    summary: str = Field(max_length=5000)
    assessment: str = Field(max_length=3000)
    claims: list[ClaimDraft] = Field(default_factory=list, max_length=12)
    positive_factors: list[FactorDraft] = Field(default_factory=list, max_length=6)
    negative_factors: list[FactorDraft] = Field(default_factory=list, max_length=6)
    uncertainties: list[str] = Field(default_factory=list, max_length=12)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=6)
    data_cutoff: date = Field(description="Today's date from system context, not an invented future date")
