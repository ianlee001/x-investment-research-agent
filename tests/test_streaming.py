import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from app.agent.streaming import assistant_text
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph

TOOL_RESULT = json.dumps(
    {
        "available": True,
        "provider": "tavily",
        "documents": [{"title": "News fixture", "excerpt": "A saved news passage."}],
    }
)


@pytest.mark.parametrize(
    "message",
    [
        ToolMessage(content=TOOL_RESULT, tool_call_id="search-1"),
        ToolMessage(content=[{"type": "text", "text": TOOL_RESULT}], tool_call_id="search-2"),
        HumanMessage(content="Do not echo user messages into the answer stream"),
        SystemMessage(content="Do not expose instructions"),
    ],
)
def test_non_assistant_messages_never_become_answer_text(message):
    assert assistant_text(message) == ""


def test_text_chunks_preserve_normal_text_without_removing_json_by_guesswork():
    assert assistant_text(AIMessageChunk(content="正在查询新闻。")) == "正在查询新闻。"
    # An explicitly requested JSON answer is legitimate assistant output.
    assert assistant_text(AIMessageChunk(content='{"answer": 42}')) == '{"answer": 42}'
    assert (
        assistant_text(
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "tavily_search",
                        "args": '{"query":"SNDK"}',
                        "id": "call-1",
                        "index": 0,
                    }
                ],
            )
        )
        == ""
    )
    assert (
        assistant_text(
            AIMessageChunk(
                content=[
                    {"type": "reasoning", "reasoning": "Internal reasoning"},
                    {"type": "thinking", "thinking": "Internal thinking"},
                    {"type": "tool_call", "name": "tavily_search", "args": {"query": "SNDK"}},
                    {"type": "text", "text": "保留正文。"},
                    {"type": "image", "url": "https://example.com/image.png"},
                    {"type": "text", "text": "继续回答。"},
                ]
            )
        )
        == "保留正文。继续回答。"
    )


async def test_native_langgraph_tool_results_are_excluded_from_public_stream():
    graph = StateGraph(MessagesState)
    graph.add_node(
        "model",
        lambda state: {
            "messages": [
                AIMessage(
                    content="正在查询新闻。",
                    tool_calls=[
                        {
                            "name": "search",
                            "args": {},
                            "id": "search-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
    )
    graph.add_node(
        "tools", lambda state: {"messages": [ToolMessage(content=TOOL_RESULT, tool_call_id="search-1")]}
    )
    graph.add_node(
        "answer",
        lambda state: {"messages": [AIMessage(content="这是有来源的最终回答。中英文 UTF-8 都保留。")]},
    )
    graph.add_edge(START, "model")
    graph.add_edge("model", "tools")
    graph.add_edge("tools", "answer")
    graph.add_edge("answer", END)
    observed, public = [], []
    async for message, _metadata in graph.compile().astream(
        {"messages": [HumanMessage(content="查询最近新闻")]},
        stream_mode="messages",
    ):
        observed.append(message)
        public.append(assistant_text(message))
    assert any(isinstance(message, ToolMessage) for message in observed)
    assert "".join(public) == "正在查询新闻。这是有来源的最终回答。中英文 UTF-8 都保留。"
    assert TOOL_RESULT not in "".join(public)


@pytest.mark.integration
async def test_worker_persists_only_assistant_deltas_then_saves_final_answer(pg, monkeypatch):
    from app import worker
    from app.db import session_scope, uid
    from app.models import Message, Run, RunEvent, Thread
    from sqlalchemy import select

    final = "根据保存的资料，仍有不确定性。"
    pieces = [
        AIMessageChunk(content="正在查询新闻。"),
        ToolMessage(content=TOOL_RESULT, tool_call_id="search-1"),
        ToolMessage(content=[{"type": "text", "text": TOOL_RESULT}], tool_call_id="search-2"),
        AIMessageChunk(content=[{"type": "text", "text": final}]),
    ]

    class AgentFixture:
        async def aget_state(self, config):
            return SimpleNamespace(
                values={"messages": [AIMessage(content=final)]}, next=(), interrupts=(), tasks=()
            )

        async def astream(self, *args, **kwargs):
            for piece in pieces:
                yield "messages", (piece, {})
            yield "updates", {"tools": {"messages": [pieces[1]]}}

    @asynccontextmanager
    async def tools_fixture(http):
        yield [], []

    monkeypatch.setattr(worker, "agent_tools", tools_fixture)
    monkeypatch.setattr(worker, "build_agent", lambda *args, **kwargs: AgentFixture())
    run_id, thread_id = uid(), uid()
    async with session_scope() as db:
        db.add(Thread(id=thread_id))
        db.add(Run(id=run_id, thread_id=thread_id, kind="chat", question="stream fixture", status="running"))
    await worker.execute_run(run_id, *pg)
    async with session_scope() as db:
        run = await db.get(Run, run_id)
        deltas = list(
            await db.scalars(
                select(RunEvent)
                .where(
                    RunEvent.run_id == run_id,
                    RunEvent.type == "assistant_delta",
                )
                .order_by(RunEvent.id)
            )
        )
        message = await db.scalar(
            select(Message).where(Message.run_id == run_id, Message.role == "assistant")
        )
    assert run.status == "completed"
    assert "".join(event.data["text"] for event in deltas) == "正在查询新闻。" + final
    assert message.content == final
    assert run.result["answer"] == final
