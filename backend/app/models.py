from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now, uid


class Account(Base):
    __tablename__ = "tracked_x_accounts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # X snowflakes stay strings.
    username: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    profile_image_url: Mapped[str | None] = mapped_column(Text)
    since_id: Mapped[str | None] = mapped_column(String(40))
    sync_cursor: Mapped[dict | None] = mapped_column(JSONB)
    sync_status: Mapped[str] = mapped_column(String(30), default="idle")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Post(Base):
    __tablename__ = "x_posts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    author_id: Mapped[str] = mapped_column(String(40), index=True)  # Search authors need not be tracked.
    username: Mapped[str] = mapped_column(String(32), default="")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    tickers: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    references: Mapped[list] = mapped_column(JSONB, default=list)
    edit_history_ids: Mapped[list] = mapped_column(JSONB, default=list)
    unavailable: Mapped[bool] = mapped_column(Boolean, default=False)


class WatchItem(Base):
    __tablename__ = "watchlist"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    thesis: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Thread(Base):
    __tablename__ = "chat_threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(180), default="新的研究对话")
    checkpoint_id: Mapped[str] = mapped_column(String(36), default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Run(Base):
    __tablename__ = "research_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    thread_id: Mapped[str] = mapped_column(String(80), index=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(30), default="research")
    question: Mapped[str] = mapped_column(Text)
    ticker: Mapped[str | None] = mapped_column(String(16))
    post_id: Mapped[str | None] = mapped_column(String(40))
    request_key: Mapped[str] = mapped_column(String(150), unique=True, default=uid)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(100), default="等待执行")
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    resume_payload: Mapped[dict | None] = mapped_column(JSONB)
    graph_started: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','awaiting_approval','completed','partial','failed','cancelled','expired')"
        ),
        Index(
            "uq_active_thread",
            "thread_id",
            unique=True,
            postgresql_where=__import__("sqlalchemy").text(
                "status IN ('queued','running','awaiting_approval')"
            ),
        ),
    )


class Message(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    thread_id: Mapped[str] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("research_runs.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("run_id", "role"),)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    source_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[str | None] = mapped_column(String(60))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    tickers: Mapped[list] = mapped_column(JSONB, default=list)
    assessment: Mapped[dict] = mapped_column(JSONB)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    stance: Mapped[str] = mapped_column(String(20))
    quote: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("claim_id", "source_id", "stance"),)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    interrupt_id: Mapped[str] = mapped_column(String(80))
    action_index: Mapped[int] = mapped_column(Integer)
    tool_call_id: Mapped[str] = mapped_column(String(180), default="")
    tool_name: Mapped[str] = mapped_column(String(100))
    args: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    execution_status: Mapped[str] = mapped_column(String(30), default="not_started")
    decision: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("run_id", "interrupt_id", "action_index"),)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConfigEntry(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Operation(Base):
    __tablename__ = "tool_operations"
    key: Mapped[str] = mapped_column(String(180), primary_key=True)
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProviderCache(Base):
    __tablename__ = "provider_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RateSlot(Base):
    __tablename__ = "provider_rate_slots"
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    next_at: Mapped[float] = mapped_column(Float, default=0)


class SourceProfile(Base):
    __tablename__ = "source_profiles"
    username: Mapped[str] = mapped_column(String(32), primary_key=True)
    manual_trust: Mapped[str] = mapped_column(String(30), default="unrated")
    rationale: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
