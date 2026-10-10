import pytest
from app.agent.context import RunContext
from app.agent.factory import build_agent
from app.approvals import decide, record_interrupts
from app.db import session_scope, uid
from app.models import Approval, Operation, Run, WatchItem
from app.schemas import DecisionInput
from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.types import Command
from sqlalchemy import select


class DeterministicToolModel(BaseChatModel):
    """Test fixture only. Production always uses DashScope; no provider result is simulated there."""

    actions: list[dict] = []

    @property
    def _llm_type(self):
        return "deterministic_test_fixture"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if messages[-1].type == "human":
            answer = AIMessage(content="", tool_calls=self.actions)
        else:
            answer = AIMessage(content="Action cycle finished.")
        return ChatResult(generations=[ChatGeneration(message=answer)])


async def make_pending(pg, *, actions):
    saver, store = pg
    run_id, thread_id = uid(), uid()
    async with session_scope() as db:
        db.add(
            Run(
                id=run_id,
                thread_id=thread_id,
                kind="chat",
                question="Test approved changes",
                status="running",
            )
        )
    agent = build_agent([], saver, store, research=False, model=DeterministicToolModel(actions=actions))
    config = {"configurable": {"thread_id": thread_id}}
    await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Test approved changes"}]},
        config,
        context=RunContext(run_id),
        durability="sync",
    )
    state = await agent.aget_state(config)
    assert state.interrupts
    await record_interrupts(run_id, state)
    async with session_scope() as db:
        approvals = list(
            await db.scalars(
                select(Approval).where(Approval.run_id == run_id).order_by(Approval.action_index)
            )
        )
    return run_id, config, approvals


@pytest.mark.integration
async def test_native_hitl_survives_agent_rebuild_and_executes_once(pg):
    actions = [
        {
            "name": "add_to_watchlist",
            "args": {"ticker": "AMZN", "notes": "original"},
            "id": "call_approval_test",
            "type": "tool_call",
        }
    ]
    run_id, config, approvals = await make_pending(pg, actions=actions)
    async with session_scope() as db:
        assert await db.get(WatchItem, "AMZN") is None
    updated = await decide(
        approvals[0].id,
        "edit",
        DecisionInput(args={"ticker": "AMZN", "company_name": "Amazon", "notes": "edited"}),
    )
    assert updated["execution_status"] == "not_started"
    saver, store = pg
    rebuilt = build_agent([], saver, store, research=False, model=DeterministicToolModel(actions=actions))
    async with session_scope() as db:
        resume = (await db.get(Run, run_id)).resume_payload
    await rebuilt.ainvoke(Command(resume=resume), config, context=RunContext(run_id), durability="sync")
    async with session_scope() as db:
        assert (await db.get(WatchItem, "AMZN")).notes == "edited"
        assert (await db.get(Approval, approvals[0].id)).execution_status == "executed"
        operations = list(await db.scalars(select(Operation).where(Operation.key.like(run_id + ":%"))))
        assert len(operations) == 1
    duplicate = await decide(
        approvals[0].id,
        "edit",
        DecisionInput(args={"ticker": "AMZN", "company_name": "Amazon", "notes": "edited"}),
    )
    assert duplicate["execution_status"] == "executed"
    with pytest.raises(HTTPException) as error:
        await decide(approvals[0].id, "reject", DecisionInput(reason="stale click"))
    assert error.value.status_code == 409


@pytest.mark.integration
async def test_batch_decisions_preserve_order_and_rejection_does_not_write(pg):
    actions = [
        {"name": "add_to_watchlist", "args": {"ticker": "MSFT"}, "id": "call_batch_1", "type": "tool_call"},
        {
            "name": "update_investment_preferences",
            "args": {"risk_tolerance": "balanced", "investment_horizon": "long"},
            "id": "call_batch_2",
            "type": "tool_call",
        },
    ]
    run_id, config, approvals = await make_pending(pg, actions=actions)
    assert len(approvals) == 2
    await decide(approvals[1].id, "approve", DecisionInput())
    async with session_scope() as db:
        run = await db.get(Run, run_id)
        assert run.status == "awaiting_approval" and run.resume_payload is None
    await decide(approvals[0].id, "reject", DecisionInput(reason="Do not add this stock"))
    async with session_scope() as db:
        resume = (await db.get(Run, run_id)).resume_payload
    decisions = next(iter(resume.values()))["decisions"]
    assert [d["type"] for d in decisions] == ["reject", "approve"]
    saver, store = pg
    agent = build_agent([], saver, store, research=False, model=DeterministicToolModel(actions=actions))
    await agent.ainvoke(Command(resume=resume), config, context=RunContext(run_id), durability="sync")
    async with session_scope() as db:
        assert await db.get(WatchItem, "MSFT") is None
    item = await store.aget(("local", "preferences"), "investment")
    assert item.value == {"risk_tolerance": "balanced", "investment_horizon": "long"}


@pytest.mark.integration
async def test_new_store_connection_reads_long_term_memory(pg):
    saver, store = pg
    await store.aput(("local", "preferences"), "restart_check", {"risk": "balanced"})
    from app.config import get_settings
    from langgraph.store.postgres.aio import AsyncPostgresStore

    async with AsyncPostgresStore.from_conn_string(get_settings().db_url) as reopened:
        item = await reopened.aget(("local", "preferences"), "restart_check")
        assert item.value == {"risk": "balanced"}
