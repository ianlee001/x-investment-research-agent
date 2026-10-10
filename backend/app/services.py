import hashlib
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import now, session_scope
from app.models import ConfigEntry, Run, RunEvent, Source
from app.schemas import AppPreferences

TERMINAL = {"completed", "partial", "failed", "cancelled", "expired"}
ACTIVE = {"queued", "running", "awaiting_approval"}


class BudgetExceeded(Exception):
    pass


class RunCancelled(Exception):
    pass


async def event(run_id: str, event_type: str, data: dict | None = None):
    async with session_scope() as db:
        db.add(RunEvent(run_id=run_id, type=event_type, data=data or {}))


async def increment_usage(run_id: str, key: str, amount: int, limit: int | None = None):
    async with session_scope() as db:
        run = await db.get(Run, run_id, with_for_update=True)
        if not run:
            raise RunCancelled("Run no longer exists")
        if run.cancel_requested or run.status in {"cancelled", "expired"}:
            raise RunCancelled("用户已取消任务")
        usage = dict(run.usage)
        next_value = usage.get(key, 0) + amount
        if limit is not None and next_value > limit:
            raise BudgetExceeded(f"已达到 {key} 上限 {limit}")
        usage[key] = next_value
        run.usage = usage


async def preferences() -> AppPreferences:
    async with session_scope() as db:
        row = await db.get(ConfigEntry, "preferences")
        return AppPreferences.model_validate(row.value) if row else AppPreferences()


async def save_preferences(value: AppPreferences):
    async with session_scope() as db:
        await db.execute(
            insert(ConfigEntry)
            .values(key="preferences", value=value.model_dump())
            .on_conflict_do_update(
                index_elements=[ConfigEntry.key], set_={"value": value.model_dump(), "updated_at": now()}
            )
        )


def safe_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


async def capture_sources(run_id: str, documents: list[dict], provider: str) -> list[dict]:
    output = []
    async with session_scope() as db:
        for document in documents[:10]:
            url = str(document.get("url", ""))
            excerpt = str(document.get("excerpt", ""))[:9000]
            if not safe_url(url) or not excerpt:
                continue
            content_hash = hashlib.sha256(excerpt.encode()).hexdigest()
            source_id = "src_" + hashlib.sha256(f"{run_id}:{url}:{content_hash}".encode()).hexdigest()[:24]
            metadata = document.get("metadata", {})
            values = {
                "id": source_id,
                "run_id": run_id,
                "provider": provider,
                "source_type": document.get("source_type", "web"),
                "title": str(document.get("title", "Source"))[:1000],
                "url": url,
                "excerpt": excerpt,
                "content_hash": content_hash,
                "published_at": str(document["published_at"])[:60] if document.get("published_at") else None,
                "metadata_json": metadata,
                "retrieved_at": now(),
            }
            await db.execute(insert(Source).values(**values).on_conflict_do_nothing())
            output.append({**document, "excerpt": excerpt, "source_id": source_id})
        if output:
            db.add(
                RunEvent(
                    run_id=run_id,
                    type="evidence_added",
                    data={
                        "count": len(output),
                        "provider": provider,
                        "sources": [
                            {"id": d["source_id"], "title": d.get("title", ""), "url": d["url"]}
                            for d in output
                        ],
                    },
                )
            )
    return output


async def enqueue(
    question: str, *, kind="research", thread_id=None, ticker=None, post_id=None, request_key=None
):
    from app.db import uid

    async with session_scope() as db:
        if request_key:
            previous = await db.scalar(select(Run).where(Run.request_key == request_key))
            if previous:
                if (previous.question, previous.kind, previous.ticker, previous.post_id) != (
                    question,
                    kind,
                    ticker,
                    post_id,
                ):
                    from fastapi import HTTPException

                    raise HTTPException(409, "幂等键已用于不同的请求")
                return previous
        run = Run(
            id=uid(),
            thread_id=thread_id or uid(),
            question=question,
            kind=kind,
            ticker=ticker,
            post_id=post_id,
            request_key=request_key or uid(),
        )
        db.add(run)
        await db.flush()
        db.add(RunEvent(run_id=run.id, type="run_queued", data={"kind": kind}))
        return run


def public_row(item) -> dict:
    """Only for business models; Settings and provider request objects must never reach this helper."""
    result = {}
    for column in item.__table__.columns:
        value = getattr(item, column.name)
        result[column.name] = value.isoformat() if hasattr(value, "isoformat") else value
    return result
