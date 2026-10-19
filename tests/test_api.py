import httpx
import pytest
from app.api import app
from app.db import session_scope, uid
from app.models import Run, RunEvent


@pytest.mark.integration
async def test_chat_citations_include_old_turns_and_exclude_other_threads(pg):
    from datetime import timedelta

    from app.db import now
    from app.models import Message, Source, Thread

    thread_id, foreign_thread = uid(), uid()
    old_id = "src_" + "a" * 24
    foreign_id = "src_" + "b" * 24
    live_id = "src_" + "c" * 24
    async with session_scope() as db:
        db.add_all([Thread(id=thread_id), Thread(id=foreign_thread)])
        await db.flush()
        runs = [
            Run(
                id=uid(),
                thread_id=thread_id,
                kind="chat",
                question="citation fixture",
                status="completed",
                created_at=now() - timedelta(minutes=20 - i),
            )
            for i in range(12)
        ]
        foreign_run = Run(id=uid(), thread_id=foreign_thread, question="foreign fixture")
        db.add_all([*runs, foreign_run])
        await db.flush()
        for source_id, run in [(old_id, runs[0]), (foreign_id, foreign_run), (live_id, runs[-1])]:
            db.add(
                Source(
                    id=source_id,
                    run_id=run.id,
                    provider="fixture",
                    source_type="web",
                    title="Fixture article",
                    url="https://example.com/article",
                    excerpt="Saved excerpt",
                    content_hash="f" * 64,
                )
            )
        db.add(
            Message(
                thread_id=thread_id,
                run_id=runs[-1].id,
                role="assistant",
                content=f"Earlier source [{old_id}]. Unrelated source [{foreign_id}].",
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/v1/chat/threads/{thread_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["runs"]) == 10
    assert runs[0].id not in {run["id"] for run in data["runs"]}
    assert {source["id"] for source in data["sources"]} == {old_id, live_id}
    assert data["messages"][0]["content"].endswith(f"[{foreign_id}].")


@pytest.mark.integration
async def test_sse_reconnect_replays_only_events_after_id(pg):
    run_id = uid()
    async with session_scope() as db:
        db.add(Run(id=run_id, thread_id=uid(), question="SSE fixture", status="completed"))
        await db.flush()
        first = RunEvent(run_id=run_id, type="stage_started", data={"stage": "first"})
        second = RunEvent(run_id=run_id, type="report_completed", data={"title": "second"})
        db.add_all([first, second])
        await db.flush()
        cursor = first.id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            f"/api/v1/research/runs/{run_id}/events", headers={"Last-Event-ID": str(cursor)}
        )
        assert response.status_code == 200
        assert "event: report_completed" in response.text
        assert "event: stage_started" not in response.text
        assert "event: stream_end" in response.text


@pytest.mark.integration
async def test_cross_origin_local_mutation_is_blocked(pg):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/watchlist", json={"ticker": "AAPL"}, headers={"Origin": "https://untrusted.example"}
        )
        assert response.status_code == 403


@pytest.mark.integration
async def test_duplicate_request_key_cannot_be_reused_for_different_work(pg):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        key = uid()
        first = await client.post(
            "/api/v1/research/runs", json={"question": "first question", "request_key": key}
        )
        second = await client.post(
            "/api/v1/research/runs", json={"question": "first question", "request_key": key}
        )
        assert first.json()["id"] == second.json()["id"]
        different = await client.post(
            "/api/v1/research/runs", json={"question": "different question", "request_key": key}
        )
        assert different.status_code == 409
