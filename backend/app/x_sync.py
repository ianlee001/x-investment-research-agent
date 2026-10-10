from datetime import datetime, timedelta

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.db import now, session_scope
from app.models import (
    Account,
    Approval,
    Claim,
    Message,
    Operation,
    Post,
    ProviderCache,
    Run,
    RunEvent,
    Source,
    SourceProfile,
    Thread,
    WatchItem,
)
from app.providers.http import ProviderError
from app.providers.x import XProvider
from app.services import event


async def store_posts(rows: list[dict]):
    async with session_scope() as db:
        for row in rows:
            values = {
                **row,
                "created_at": datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if row.get("created_at")
                else now(),
                "fetched_at": now(),
                "checked_at": now(),
                "unavailable": False,
            }
            await db.execute(
                insert(Post)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[Post.id],
                    set_={key: value for key, value in values.items() if key not in {"id", "created_at"}},
                )
            )


async def sync_account(provider: XProvider, account_id: str, run_id: str | None = None):
    # Session advisory lock survives page transactions and is released on connection close/crash.
    from app.db import engine

    async with engine.connect() as lock:
        held = await lock.scalar(
            text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": "x-sync:" + account_id}
        )
        if not held:
            return {"skipped": True, "reason": "already_syncing"}
        try:
            async with session_scope() as db:
                account = await db.get(Account, account_id)
                if not account:
                    return {"skipped": True, "reason": "account_removed"}
                cursor = dict(
                    account.sync_cursor or {"lower": account.since_id, "token": None, "newest": None}
                )
                account.sync_status, account.error = "syncing", None
                username = account.username
            count = 0
            complete = False
            for page in range(provider.http.settings.x_sync_max_pages):
                response = await provider.posts(
                    account_id,
                    since_id=cursor.get("lower"),
                    pagination_token=cursor.get("token"),
                    max_results=provider.http.settings.x_page_size,
                )
                if response.get("errors"):
                    raise ProviderError("x", "timeline_partial_errors")
                rows = provider.normalize(response, username)
                await store_posts(rows)
                count += len(rows)
                ids = [row["id"] for row in rows] + ([cursor["newest"]] if cursor.get("newest") else [])
                cursor["newest"] = max(ids, key=int) if ids else cursor.get("newest")
                cursor["token"] = response.get("meta", {}).get("next_token")
                # An initial backfill is explicitly bounded. Subsequent incrementals finish every page.
                bounded_initial = (
                    not cursor.get("lower") and page + 1 == provider.http.settings.x_sync_max_pages
                )
                complete = not cursor["token"] or bounded_initial
                async with session_scope() as db:
                    account = await db.get(Account, account_id)
                    if not account:
                        break
                    if complete:
                        account.since_id = cursor.get("newest") or account.since_id
                        account.sync_cursor = None
                        account.sync_status = "idle"
                        account.last_synced_at = now()
                    else:
                        account.sync_cursor = cursor.copy()
                if run_id:
                    await event(
                        run_id, "sync_progress", {"account": username, "posts": count, "page": page + 1}
                    )
                if complete:
                    break
            if not complete:
                async with session_scope() as db:
                    account = await db.get(Account, account_id)
                    if account:
                        account.sync_status = "more_pages"
            return {
                "posts": count,
                "complete": complete,
                "initial_backfill_limited": bounded_initial if count else False,
            }
        except ProviderError as error:
            async with session_scope() as db:
                account = await db.get(Account, account_id)
                if account:
                    account.sync_status, account.error = "error", str(error)
                    # Expired pagination tokens restart the same lower watermark, never skip newer posts.
                    if error.http_status == 400:
                        account.sync_cursor = None
            raise
        finally:
            await lock.execute(
                text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": "x-sync:" + account_id}
            )


async def withdraw_x_content(missing: set[str], checkpointer, store):
    """Conservatively withdraw affected report/chat histories, including replay and native checkpoints."""
    async with session_scope() as db:
        source_runs = select(Source.run_id).where(
            Source.source_type == "x", Source.metadata_json["post_id"].astext.in_(missing)
        )
        threads = list(
            await db.scalars(
                select(Run.thread_id).where((Run.id.in_(source_runs)) | Run.post_id.in_(missing))
            )
        )
        runs = list(await db.scalars(select(Run).where(Run.thread_id.in_(threads)).with_for_update()))
        run_ids = [run.id for run in runs]
        # Delete checkpoints before committing the withdrawal: failure rolls back business changes,
        # so the next reconciliation retries. The single worker cannot execute another graph meanwhile.
        for checkpoint_id in {run.checkpoint_id or run.thread_id for run in runs}:
            await checkpointer.adelete_thread(checkpoint_id)
        await db.execute(
            update(Post)
            .where(Post.id.in_(missing))
            .values(
                text="",
                metrics={},
                references=[],
                edit_history_ids=[],
                tickers=[],
                unavailable=True,
                checked_at=now(),
            )
        )
        # Cache keys are hashes; clear the cache even when no report used the post.
        await db.execute(delete(ProviderCache))
        if not run_ids:
            return
        await db.execute(delete(Claim).where(Claim.run_id.in_(run_ids)))  # evidence cascades
        await db.execute(
            update(Source)
            .where(Source.run_id.in_(run_ids))
            .values(
                excerpt="[相关 X 原帖已不可访问；研究内容撤回]",
                title="已撤回的研究来源",
                metadata_json={"unavailable": True},
                content_hash="",
            )
        )
        await db.execute(
            update(Message)
            .where(Message.thread_id.in_(threads))
            .values(content="[此对话涉及已不可访问的 X 内容，历史内容已撤回]")
        )
        await db.execute(delete(RunEvent).where(RunEvent.run_id.in_(run_ids)))
        for run in runs:
            run.question = "[涉及已不可访问的 X 内容，研究历史已撤回]"
            run.result = {
                "title": "报告引用的 X 原帖已不可访问",
                "summary": "相关内容已撤回，请重新研究。",
                "withdrawn": True,
            }
            run.resume_payload = None
            run.cancel_requested = True
            if run.status in {"queued", "running", "awaiting_approval"}:
                run.status, run.completed_at = "cancelled", now()
            db.add(RunEvent(run_id=run.id, type="content_withdrawn", data={"withdrawn": True}))
        approvals = list(await db.scalars(select(Approval).where(Approval.run_id.in_(run_ids))))
        for approval in approvals:
            approval.args, approval.decision, approval.description = {}, None, "相关内容已撤回"
            if approval.status == "pending":
                approval.status, approval.execution_status = "expired", "not_executed"
        for thread in await db.scalars(select(Thread).where(Thread.id.in_(threads))):
            from app.db import uid

            thread.checkpoint_id, thread.title = uid(), "已撤回的研究对话"
        for run_id in run_ids:
            operations = list(
                await db.scalars(select(Operation).where(Operation.key.startswith(run_id + ":")))
            )
            for operation in operations:
                args, tool_name = operation.result.get("args", {}), operation.result.get("tool")
                if tool_name == "save_thesis":
                    item = await db.get(WatchItem, args.get("ticker", ""))
                    if item and item.thesis == args.get("thesis"):
                        item.thesis = "[相关 X 内容已不可访问，观点已撤回]"
                    memory = await store.aget(("local", "theses"), args.get("ticker", ""))
                    if memory and memory.value.get("thesis") == args.get("thesis"):
                        await store.adelete(("local", "theses"), memory.key)
                elif tool_name == "add_to_watchlist":
                    item = await db.get(WatchItem, args.get("ticker", ""))
                    if item and item.notes == args.get("notes"):
                        item.notes = "[相关 X 内容已撤回]"
                elif tool_name == "update_source_trust":
                    item = await db.get(SourceProfile, args.get("username", "").lower())
                    if item and item.rationale == args.get("reason"):
                        item.rationale, item.manual_trust = "[相关 X 内容已撤回]", "unrated"
                        await store.adelete(("local", "source_trust"), item.username)
            await db.execute(delete(Operation).where(Operation.key.startswith(run_id + ":")))


async def reconcile_posts(provider: XProvider, checkpointer, store):
    """Recheck retained posts; APIs also suppress data whose last check is over 24 hours old."""
    async with session_scope() as db:
        ids = list(
            await db.scalars(
                select(Post.id)
                .where(Post.unavailable.is_(False), Post.checked_at < now() - timedelta(hours=6))
                .order_by(Post.checked_at)
            )
        )
    for offset in range(0, len(ids), 100):
        batch = ids[offset : offset + 100]
        response = await provider.get_posts(batch)
        rows = provider.normalize(response)
        await store_posts(rows)
        missing = set(batch) - {row["id"] for row in rows}
        if not missing:
            continue
        await withdraw_x_content(missing, checkpointer, store)


async def tracked_posts(ticker="", username="", limit=10):
    async with session_scope() as db:
        query = select(Post).where(
            Post.unavailable.is_(False), Post.checked_at >= now() - timedelta(hours=24)
        )
        if ticker:
            query = query.where(Post.tickers.contains([ticker]))
        if username:
            query = query.where(Post.username.ilike(username.lstrip("@")))
        rows = list(await db.scalars(query.order_by(Post.created_at.desc()).limit(min(20, max(1, limit)))))
        result = [
            {
                "id": row.id,
                "author_id": row.author_id,
                "username": row.username,
                "text": row.text,
                "created_at": row.created_at.isoformat(),
                "tickers": row.tickers,
            }
            for row in rows
        ]
    return {
        "available": True,
        "provider": "x",
        "data": {"count": len(result), "scope": "locally_tracked_posts_checked_within_24h"},
        "documents": [XProvider.document(row) for row in result],
    }
