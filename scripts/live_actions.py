"""Opt-in real X ingestion and real-model HITL checks; never auto-approve personal changes."""

import argparse
import asyncio
import json
import logging
import sys

import httpx
from app.config import ROOT, get_settings
from app.db import session_scope
from app.models import Account
from app.providers.http import ProviderHTTP
from app.providers.x import XProvider
from app.x_sync import sync_account
from sqlalchemy.dialects.postgresql import insert


async def x_sync():
    http = ProviderHTTP()
    http.settings = http.settings.model_copy(update={"x_sync_max_pages": 1, "x_page_size": 5})
    try:
        provider = XProvider(http)
        user = await provider.user("NVIDIA")
        async with session_scope() as db:
            await db.execute(
                insert(Account)
                .values(
                    id=user["id"],
                    username=user["username"],
                    name=user.get("name", ""),
                    description=user.get("description", ""),
                    profile_image_url=user.get("profile_image_url"),
                )
                .on_conflict_do_nothing()
            )
        result = await sync_account(provider, user["id"])
        print(json.dumps({"username": user["username"], **result}))
    finally:
        await http.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["chat-start", "chat-status", "chat-reject", "x-sync"])
    args = parser.parse_args()
    if args.action == "x-sync":
        asyncio.run(x_sync())
        return
    settings = get_settings()
    secret = settings.app_auth_token.get_secret_value()
    headers = {"Authorization": "Bearer " + secret} if secret else {}
    state_path = ROOT / ".runtime" / "live-actions.json"
    with httpx.Client(
        base_url=f"http://127.0.0.1:{settings.app_port}/api/v1", headers=headers, trust_env=False, timeout=30
    ) as client:
        if args.action == "chat-start":
            response = client.post("/chat/threads")
            response.raise_for_status()
            thread = response.json()
            response = client.post(
                f"/chat/threads/{thread['id']}/messages",
                json={
                    "content": "验收测试：请调用 add_to_watchlist 工具，提出将 AAPL 加入关注列表的操作，notes 为 end-to-end check。等待网页审批，不要把口头答复当成执行。无需调用外部行情。",
                },
            )
            response.raise_for_status()
            run = response.json()
            state = {"thread_id": thread["id"], "run_id": run["id"]}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            print(json.dumps({**state, "status": run["status"]}))
            return
        state = json.loads(state_path.read_text(encoding="utf-8"))
        response = client.get(f"/research/runs/{state['run_id']}")
        response.raise_for_status()
        run = response.json()
        if args.action == "chat-reject":
            for approval in run["approvals"]:
                if approval["status"] == "pending":
                    response = client.post(
                        f"/approvals/{approval['id']}/reject",
                        json={"reason": "验收拒绝分支；不修改个人关注列表"},
                    )
                    response.raise_for_status()
            print(json.dumps({"rejection_submitted": True, "run_id": run["id"]}))
            return
        result = {
            **state,
            "status": run["status"],
            "error": run["error"],
            "usage": run["usage"],
            "approvals": [
                {key: a[key] for key in ("id", "tool_name", "status", "execution_status")}
                for a in run["approvals"]
            ],
            "answer": (run.get("result") or {}).get("answer"),
        }
        print(json.dumps(result, ensure_ascii=True))
        state_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error_type": type(error).__name__, "code": getattr(error, "code", None)}
            )
        )
        raise SystemExit(1) from None
