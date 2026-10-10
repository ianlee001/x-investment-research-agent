from types import SimpleNamespace

import pytest
from app.db import session_scope
from app.models import Account, Post
from app.providers.http import ProviderError
from app.providers.x import XProvider
from app.x_sync import sync_account
from sqlalchemy import select


def page(ids, next_token=None):
    return {
        "data": [
            {"id": value, "author_id": "1001", "text": "$NVDA sample", "created_at": "2026-10-01T12:00:00Z"}
            for value in ids
        ],
        "meta": {"next_token": next_token} if next_token else {},
    }


class TimelineFixture:
    normalize = staticmethod(XProvider.normalize)

    def __init__(self, responses):
        self.responses, self.calls = responses, []
        self.http = SimpleNamespace(settings=SimpleNamespace(x_sync_max_pages=1, x_page_size=5))

    async def posts(self, user_id, **kwargs):
        self.calls.append(kwargs)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.integration
async def test_incremental_watermark_advances_only_after_last_page(pg):
    async with session_scope() as db:
        db.add(Account(id="1001", username="fixture_one", since_id="10"))
    first = TimelineFixture([page(["40", "30"], "page2")])
    assert (await sync_account(first, "1001"))["complete"] is False
    async with session_scope() as db:
        account = await db.get(Account, "1001")
        assert account.since_id == "10" and account.sync_cursor["newest"] == "40"
    failed = TimelineFixture([ProviderError("x", "network_unavailable")])
    with pytest.raises(ProviderError):
        await sync_account(failed, "1001")
    second = TimelineFixture([page(["20"])])
    assert (await sync_account(second, "1001"))["complete"] is True
    assert second.calls[0]["since_id"] == "10" and second.calls[0]["pagination_token"] == "page2"
    async with session_scope() as db:
        assert (await db.get(Account, "1001")).since_id == "40"
        ids = set(await db.scalars(select(Post.id).where(Post.author_id == "1001")))
        assert ids == {"20", "30", "40"}


@pytest.mark.integration
async def test_partial_x_response_does_not_advance_cursor(pg):
    async with session_scope() as db:
        db.add(Account(id="1002", username="fixture_two", since_id="10"))
    provider = TimelineFixture([{**page(["50"]), "errors": [{"title": "partial response"}]}])
    with pytest.raises(ProviderError):
        await sync_account(provider, "1002")
    async with session_scope() as db:
        assert (await db.get(Account, "1002")).since_id == "10"


def test_long_text_and_ids_remain_intact():
    data = {
        "data": [
            {
                "id": "1987654321098765432",
                "author_id": "1003",
                "text": "short",
                "note_tweet": {"text": "long text $NVDA"},
            }
        ]
    }
    result = XProvider.normalize(data)
    assert result[0]["id"] == "1987654321098765432"
    assert result[0]["text"] == "long text $NVDA"
    assert result[0]["tickers"] == ["NVDA"]


@pytest.mark.integration
async def test_unavailable_x_content_withdraws_evidence_events_and_native_checkpoint(pg):
    from app.db import now
    from app.models import Approval, Claim, Evidence, Message, Run, RunEvent, Source, Thread
    from app.services import capture_sources
    from app.x_sync import store_posts, withdraw_x_content
    from test_agent_persistence import make_pending

    run_id, config, approvals = await make_pending(
        pg,
        actions=[
            {
                "name": "add_to_watchlist",
                "args": {"ticker": "NVDA", "notes": "fixture X quotation"},
                "id": "call_withdraw_test",
                "type": "tool_call",
            }
        ],
    )
    post = XProvider.normalize(page(["99999999"]))[0]
    await store_posts([post])
    documents = await capture_sources(run_id, [XProvider.document(post)], "x")
    async with session_scope() as db:
        run = await db.get(Run, run_id)
        run.result = {"summary": "fixture X quotation"}
        db.add(Thread(id=run.thread_id))
        await db.flush()
        db.add(
            Message(thread_id=run.thread_id, run_id=run_id, role="assistant", content="fixture X quotation")
        )
        db.add(RunEvent(run_id=run_id, type="assistant_delta", data={"text": "fixture X quotation"}))
        claim = Claim(
            run_id=run_id, text="fixture X quotation", kind="fact", status="supported", assessment={}
        )
        db.add(claim)
        await db.flush()
        db.add(
            Evidence(
                claim_id=claim.id,
                source_id=documents[0]["source_id"],
                stance="support",
                quote=post["text"],
                rationale="test",
            )
        )
    saver, store = pg
    assert await saver.aget_tuple(config) is not None
    await withdraw_x_content({post["id"]}, saver, store)
    assert await saver.aget_tuple(config) is None
    async with session_scope() as db:
        post_row = await db.get(Post, post["id"])
        assert post_row.unavailable and not post_row.text and post_row.checked_at <= now()
        assert (await db.get(Run, run_id)).result["withdrawn"]
        assert (await db.get(Run, run_id)).status == "cancelled"
        assert (await db.get(Approval, approvals[0].id)).args == {}
        assert not list(await db.scalars(select(Claim).where(Claim.run_id == run_id)))
        assert (await db.get(Source, documents[0]["source_id"])).metadata_json["unavailable"]
        assert all(
            event.type == "content_withdrawn"
            for event in await db.scalars(select(RunEvent).where(RunEvent.run_id == run_id))
        )
