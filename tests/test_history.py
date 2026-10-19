from datetime import timedelta

import httpx
import pytest
from app.api import app
from app.db import now, session_scope, uid
from app.models import Approval, Claim, Evidence, Message, Operation, Run, RunEvent, Source, Thread, WatchItem
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def history_fixture(pg, *, kind="research", status="completed"):
    saver, store = pg
    run_id, thread_id, checkpoint_id, current_checkpoint = uid(), uid(), uid(), uid()
    ticker = "D" + run_id.replace("-", "")[:6].upper()
    source_id = "src_" + run_id.replace("-", "")[:24]
    async with session_scope() as db:
        if kind == "chat":
            db.add(Thread(id=thread_id, checkpoint_id=current_checkpoint, title="Delete fixture"))
        run = Run(
            id=run_id,
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            kind=kind,
            question="Delete fixture",
            status=status,
            result={"summary": "Saved report"},
        )
        db.add(run)
        db.add(WatchItem(ticker=ticker, thesis="Saved personal thesis"))
        await db.flush()
        source = Source(
            id=source_id,
            run_id=run_id,
            source_type="web",
            provider="fixture",
            title="Saved article",
            url="https://example.com/fixture",
            excerpt="Evidence.",
            content_hash="f" * 64,
        )
        claim = Claim(run_id=run_id, text="Fixture fact", kind="fact", status="supported", assessment={})
        db.add_all([source, claim])
        await db.flush()
        db.add(
            Evidence(
                claim_id=claim.id,
                source_id=source_id,
                stance="support",
                quote="Evidence.",
                rationale="Fixture",
            )
        )
        if kind == "chat":
            db.add(Message(thread_id=thread_id, run_id=run_id, role="assistant", content="Saved answer"))
        approval = Approval(
            run_id=run_id,
            interrupt_id=uid(),
            action_index=0,
            tool_name="add_to_watchlist",
            args={"ticker": ticker},
            status="rejected",
            expires_at=now() + timedelta(days=1),
        )
        db.add(approval)
        db.add(RunEvent(run_id=run_id, type="assistant_delta", data={"text": "Saved answer"}))
        db.add(Operation(key=f"{run_id}:call-fixture", result={"executed": False}))
    graph = StateGraph(MessagesState)
    graph.add_node("answer", lambda state: {"messages": [AIMessage(content="Saved graph state")]})
    graph.add_edge(START, "answer")
    graph.add_edge("answer", END)
    checkpoint_ids = [checkpoint_id, current_checkpoint] if kind == "chat" else [checkpoint_id]
    for value in checkpoint_ids:
        await graph.compile(checkpointer=saver).ainvoke(
            {"messages": [HumanMessage(content="Graph fixture")]},
            config={"configurable": {"thread_id": value}},
        )
    await store.aput(("local", "preferences"), run_id, {"keep": "personal preference"})
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "source_id": source_id,
        "claim_id": claim.id,
        "approval_id": approval.id,
        "ticker": ticker,
        "checkpoints": checkpoint_ids,
    }


async def assert_erased(pg, fixture):
    saver, store = pg
    async with session_scope() as db:
        assert await db.get(Run, fixture["run_id"]) is None
        assert await db.get(Source, fixture["source_id"]) is None
        assert await db.get(Claim, fixture["claim_id"]) is None
        assert not list(await db.scalars(select(Evidence).where(Evidence.claim_id == fixture["claim_id"])))
        assert await db.get(Approval, fixture["approval_id"]) is None
        assert not list(await db.scalars(select(RunEvent).where(RunEvent.run_id == fixture["run_id"])))
        assert not list(await db.scalars(select(Message).where(Message.run_id == fixture["run_id"])))
        assert await db.get(Operation, f"{fixture['run_id']}:call-fixture") is None
        assert (await db.get(WatchItem, fixture["ticker"])).thesis == "Saved personal thesis"
    for value in fixture["checkpoints"]:
        assert await saver.aget_tuple({"configurable": {"thread_id": value}}) is None
    assert (await store.aget(("local", "preferences"), fixture["run_id"])).value[
        "keep"
    ] == "personal preference"


@pytest.mark.parametrize("kind", ["research", "daily_brief"])
async def test_delete_research_cleans_report_sources_checkpoints_but_keeps_personal_data(pg, kind):
    fixture = await history_fixture(pg, kind=kind)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.delete(f"/api/v1/research/runs/{fixture['run_id']}")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        assert (await client.get(f"/api/v1/research/runs/{fixture['run_id']}")).status_code == 404
    await assert_erased(pg, fixture)


async def test_delete_conversation_cleans_all_turns_and_rotated_checkpoints(pg):
    fixture = await history_fixture(pg, kind="chat")
    unrelated = await history_fixture(pg, kind="chat")
    async with session_scope() as db:
        second_id = uid()
        db.add(
            Run(
                id=second_id,
                thread_id=fixture["thread_id"],
                kind="chat",
                question="Second turn",
                status="cancelled",
            )
        )
        await db.flush()
        db.add(Message(thread_id=fixture["thread_id"], run_id=second_id, role="user", content="Second turn"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.delete(f"/api/v1/chat/threads/{fixture['thread_id']}")
        assert response.status_code == 200
        assert (await client.get(f"/api/v1/chat/threads/{fixture['thread_id']}")).status_code == 404
        assert (await client.get(f"/api/v1/chat/threads/{unrelated['thread_id']}")).status_code == 200
    await assert_erased(pg, fixture)
    async with session_scope() as db:
        assert await db.get(Thread, fixture["thread_id"]) is None
        assert await db.get(Run, second_id) is None
        assert await db.get(Run, unrelated["run_id"]) is not None
    assert await pg[0].aget_tuple({"configurable": {"thread_id": unrelated["checkpoints"][0]}}) is not None


@pytest.mark.parametrize("kind", ["research", "chat"])
@pytest.mark.parametrize("status", ["queued", "running", "awaiting_approval"])
async def test_active_history_must_be_stopped_before_deletion(pg, kind, status):
    fixture = await history_fixture(pg, kind=kind, status=status)
    path = (
        f"research/runs/{fixture['run_id']}" if kind == "research" else f"chat/threads/{fixture['thread_id']}"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.delete("/api/v1/" + path)
        assert response.status_code == 409
        threads = (await client.get("/api/v1/chat/threads")).json()
        if kind == "chat":
            assert next(thread for thread in threads if thread["id"] == fixture["thread_id"])[
                "has_active_run"
            ]
    async with session_scope() as db:
        assert (await db.get(Run, fixture["run_id"])).status == status
    assert await pg[0].aget_tuple({"configurable": {"thread_id": fixture["checkpoints"][0]}}) is not None


async def test_failed_deletion_rolls_back_native_checkpoints_and_business_rows(pg, monkeypatch):
    fixture = await history_fixture(pg)
    original = AsyncPostgresSaver.adelete_thread

    async def fail_after_deleting(self, thread_id):
        await original(self, thread_id)
        raise RuntimeError("Injected cleanup failure")

    monkeypatch.setattr(AsyncPostgresSaver, "adelete_thread", fail_after_deleting)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver"
    ) as client:
        assert (await client.delete(f"/api/v1/research/runs/{fixture['run_id']}")).status_code == 500
    async with session_scope() as db:
        assert await db.get(Run, fixture["run_id"]) is not None
        assert await db.get(Source, fixture["source_id"]) is not None
    assert await pg[0].aget_tuple({"configurable": {"thread_id": fixture["checkpoints"][0]}}) is not None


async def test_empty_thread_and_invalid_delete_targets(pg):
    fixture = await history_fixture(pg, kind="chat")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        thread = (await client.post("/api/v1/chat/threads")).json()
        assert (await client.delete(f"/api/v1/chat/threads/{thread['id']}")).status_code == 200
        assert (await client.delete(f"/api/v1/chat/threads/{thread['id']}")).status_code == 404
        assert (await client.delete(f"/api/v1/research/runs/{uid()}")).status_code == 404
        assert (await client.delete(f"/api/v1/research/runs/{fixture['run_id']}")).status_code == 400


async def test_send_and_delete_race_never_leaves_an_orphan_run(pg):
    import asyncio

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        thread = (await client.post("/api/v1/chat/threads")).json()
        deleted, sent = await asyncio.gather(
            client.delete(f"/api/v1/chat/threads/{thread['id']}"),
            client.post(
                f"/api/v1/chat/threads/{thread['id']}/messages",
                json={"content": "Fixture question", "request_key": uid()},
            ),
        )
    assert (deleted.status_code, sent.status_code) in {(200, 404), (409, 202)}
    async with session_scope() as db:
        runs = list(await db.scalars(select(Run).where(Run.thread_id == thread["id"])))
        saved = await db.get(Thread, thread["id"])
        assert bool(runs) == bool(saved)
