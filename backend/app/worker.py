import asyncio
import logging
from contextlib import suppress

import psycopg
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.agent.context import RunContext
from app.agent.factory import agent_tools, build_agent
from app.approvals import record_interrupts
from app.config import get_settings
from app.db import now, session_scope
from app.models import Approval, ConfigEntry, Message, Run, RunEvent, Thread
from app.providers.http import ProviderError, ProviderHTTP, current_run
from app.providers.x import XProvider
from app.reports import finalize_report
from app.scheduler import create_scheduler, enqueue_reconciliation
from app.schemas import ReportDraft
from app.services import BudgetExceeded, RunCancelled, event, preferences
from app.x_sync import reconcile_posts, sync_account

log = logging.getLogger(__name__)


async def set_terminal(run_id: str, status: str, error=None):
    async with session_scope() as db:
        run = await db.get(Run, run_id, with_for_update=True)
        run.status, run.error, run.completed_at, run.resume_payload = status, error, now(), None
        run.stage = {
            "completed": "研究完成",
            "partial": "部分完成",
            "failed": "执行失败",
            "cancelled": "已取消",
            "expired": "审批过期",
        }.get(status, status)
        db.add(RunEvent(run_id=run_id, type="run_" + status, data={"status": status, "error": error}))
        if status in {"failed", "cancelled", "expired"}:
            await db.execute(
                update(Approval)
                .where(Approval.run_id == run_id, Approval.status == "pending")
                .values(status="expired", execution_status="not_executed")
            )
        if status in {"failed", "cancelled", "expired", "partial"} and run.kind == "chat":
            from app.db import uid

            thread = await db.get(Thread, run.thread_id)
            if thread:
                thread.checkpoint_id = uid()  # A cancelled tool cycle must not poison the next user turn.


async def execute_run(run_id: str, checkpointer, store):
    settings = get_settings()
    async with session_scope() as db:
        run = await db.get(Run, run_id)
        kind, question, thread_id = run.kind, run.question, run.thread_id
        checkpoint_id = run.checkpoint_id or thread_id
        ticker, post_id, resume = run.ticker, run.post_id, run.resume_payload
    http = ProviderHTTP()
    token = current_run.set(run_id)
    try:
        async with asyncio.timeout(settings.run_timeout_seconds):
            if kind == "sync":
                result = await sync_account(XProvider(http), post_id, run_id)
                async with session_scope() as db:
                    (await db.get(Run, run_id)).result = result
                await set_terminal(run_id, "completed")
                return
            if kind == "reconcile":
                await reconcile_posts(XProvider(http), checkpointer, store)
                await set_terminal(run_id, "completed")
                return
            await event(run_id, "stage_started", {"stage": "连接研究工具"})
            async with agent_tools(http) as (tools, notices):
                agent = build_agent(tools, checkpointer, store, research=kind != "chat", notices=notices)
                config = {"configurable": {"thread_id": checkpoint_id}, "recursion_limit": 65}
                snapshot = await agent.aget_state(config)
                has_input = any(
                    message.id == "user:" + run_id for message in snapshot.values.get("messages", [])
                )
                if resume:
                    agent_input = Command(resume=resume)
                elif has_input:
                    agent_input = (
                        None  # Continue a checkpoint, including a graph completed before business commit.
                    )
                else:
                    prompt = (
                        question
                        + (f"\n目标 ticker: {ticker}" if ticker else "")
                        + (f"\nX post_id: {post_id}" if post_id else "")
                    )
                    agent_input = {"messages": [HumanMessage(content=prompt, id="user:" + run_id)]}
                async with session_scope() as db:
                    active = await db.get(Run, run_id)
                    active.graph_started, active.stage = True, "收集与核对证据"
                await event(run_id, "stage_started", {"stage": "收集与核对证据"})
                # Final state is read from the checkpoint; browser connectivity never owns execution.
                if agent_input is not None or snapshot.next:
                    buffer = ""
                    async for mode, chunk in agent.astream(
                        agent_input,
                        config=config,
                        context=RunContext(run_id),
                        stream_mode=["messages", "updates"],
                        durability="sync",
                    ):
                        if mode == "messages":
                            message, metadata = chunk
                            content = message.content
                            if isinstance(content, str) and content:
                                buffer += content
                                if len(buffer) >= 100:
                                    await event(run_id, "assistant_delta", {"text": buffer})
                                    buffer = ""
                    if buffer:
                        await event(run_id, "assistant_delta", {"text": buffer})
                snapshot = await agent.aget_state(config)
                if snapshot.interrupts or any(task.interrupts for task in snapshot.tasks):
                    await record_interrupts(run_id, snapshot)
                    return
                state = snapshot.values
                if kind == "chat":
                    messages = [
                        message
                        for message in state.get("messages", [])
                        if message.type == "ai" and not getattr(message, "tool_calls", None)
                    ]
                    content = messages[-1].content if messages else "本轮执行结束，但没有生成回答。"
                    if not isinstance(content, str):
                        content = "\n".join(
                            part.get("text", "") for part in content if isinstance(part, dict)
                        )
                    async with session_scope() as db:
                        await db.execute(
                            insert(Message)
                            .values(thread_id=thread_id, run_id=run_id, role="assistant", content=content)
                            .on_conflict_do_nothing()
                        )
                        active = await db.get(Run, run_id)
                        active.result = {"answer": content}
                        thread = await db.get(Thread, thread_id)
                        if thread:
                            thread.updated_at = now()
                    await event(run_id, "chat_completed", {"answer": content})
                else:
                    raw = state.get("structured_response")
                    if not raw:
                        raise ValueError("missing_structured_report")
                    draft = raw if isinstance(raw, ReportDraft) else ReportDraft.model_validate(raw)
                    report = await finalize_report(run_id, draft)
                    await event(
                        run_id, "report_completed", {"title": report["title"], "coverage": report["coverage"]}
                    )
                async with session_scope() as db:
                    active = await db.get(Run, run_id)
                    partial = bool(active.usage.get("unavailable_tools")) or (
                        kind != "chat" and not active.result.get("sources")
                    )
                await set_terminal(run_id, "partial" if partial else "completed")
    except (RunCancelled, asyncio.CancelledError):
        # On worker shutdown CancelledError is propagated; a checkpoint is recovered on next boot.
        if asyncio.current_task().cancelling():
            raise
        await set_terminal(run_id, "cancelled")
    except BudgetExceeded as error:
        await set_terminal(run_id, "partial", str(error))
    except TimeoutError:
        await set_terminal(run_id, "failed", "执行超过单次时间预算；已保留取证记录")
    except Exception as error:
        # Never persist raw provider/SDK exceptions (they may contain secret request URLs).
        message = (
            str(error) if isinstance(error, ProviderError) else f"{type(error).__name__}；请查看本地诊断记录"
        )
        log.error("run=%s error_type=%s", run_id, type(error).__name__)
        await set_terminal(run_id, "failed", message)
    finally:
        current_run.reset(token)
        await http.close()


async def heartbeat(stop: asyncio.Event):
    while not stop.is_set():
        async with session_scope() as db:
            await db.execute(
                insert(ConfigEntry)
                .values(key="worker", value={"heartbeat_at": now().isoformat()})
                .on_conflict_do_update(
                    index_elements=[ConfigEntry.key],
                    set_={"value": {"heartbeat_at": now().isoformat()}, "updated_at": now()},
                )
            )
            await db.execute(update(Run).where(Run.status == "running").values(heartbeat_at=now()))
            expired = list(
                await db.scalars(
                    select(Run.id)
                    .join(Approval)
                    .where(Run.status == "awaiting_approval", Approval.expires_at < now())
                    .distinct()
                )
            )
        for run_id in expired:
            await set_terminal(run_id, "expired", "审批已超过有效期")
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except TimeoutError:
            pass


async def run_worker():
    settings = get_settings()
    lock = await psycopg.AsyncConnection.connect(settings.db_url, autocommit=True, connect_timeout=8)
    cursor = await lock.execute("SELECT pg_try_advisory_lock(791486201)")
    if not (await cursor.fetchone())[0]:
        await lock.close()
        raise RuntimeError("A worker is already running for this database")
    stop = asyncio.Event()
    scheduler = None
    heartbeat_task = None
    try:
        async with AsyncConnectionPool(
            settings.db_url,
            min_size=2,
            max_size=10,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        ) as pool:
            checkpointer = AsyncPostgresSaver(
                pool, serde=JsonPlusSerializer(allowed_msgpack_modules=[("app.schemas", "ReportDraft")])
            )
            store = AsyncPostgresStore(pool)
            await checkpointer.setup()
            await store.setup()
            async with session_scope() as db:
                await db.execute(
                    update(Run)
                    .where(Run.status == "running")
                    .values(status="queued", stage="进程恢复后继续执行")
                )
            scheduler = await create_scheduler()
            await enqueue_reconciliation()
            heartbeat_task = asyncio.create_task(heartbeat(stop))
            prefs_snapshot = (await preferences()).model_dump()
            log.info("Worker ready; PostgreSQL checkpoints and store initialized")
            checks = 0
            while True:
                async with session_scope() as db:
                    run = await db.scalar(
                        select(Run)
                        .where(Run.status == "queued")
                        .order_by(Run.created_at)
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    run_id = run.id if run else None
                    if run:
                        run.status, run.started_at, run.heartbeat_at = (
                            "running",
                            run.started_at or now(),
                            now(),
                        )
                        db.add(RunEvent(run_id=run.id, type="run_started", data={"kind": run.kind}))
                if run_id:
                    execution = asyncio.create_task(execute_run(run_id, checkpointer, store))
                    while not execution.done():
                        try:
                            await asyncio.wait_for(asyncio.shield(execution), timeout=1)
                        except TimeoutError:
                            async with session_scope() as db:
                                current = await db.get(Run, run_id)
                                cancelled = current.cancel_requested
                            if cancelled:
                                execution.cancel()
                                with suppress(asyncio.CancelledError):
                                    await execution
                                await set_terminal(run_id, "cancelled")
                    with suppress(asyncio.CancelledError):
                        await execution
                else:
                    await asyncio.sleep(1)
                checks += 1
                if checks % 20 == 0:
                    fresh = (await preferences()).model_dump()
                    if fresh != prefs_snapshot:
                        scheduler.reschedule_job(
                            "x-sync", trigger="interval", minutes=fresh["sync_interval_minutes"]
                        )
                        scheduler.reschedule_job(
                            "daily-brief",
                            trigger="cron",
                            hour=fresh["daily_brief_hour"],
                            minute=0,
                            timezone=fresh["timezone"],
                        )
                        prefs_snapshot = fresh
    finally:
        stop.set()
        if scheduler:
            scheduler.shutdown(wait=False)
        if heartbeat_task:
            await heartbeat_task
        await lock.close()
