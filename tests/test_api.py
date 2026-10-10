import httpx
import pytest
from app.api import app
from app.db import session_scope, uid
from app.models import Run, RunEvent


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
