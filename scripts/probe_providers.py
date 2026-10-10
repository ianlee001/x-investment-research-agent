"""Opt-in live smoke checks. Emits only sanitized capability summaries, never credentials."""

import asyncio
import json
import logging
import sys

from app.config import ROOT, get_settings
from app.providers.http import ProviderHTTP
from app.providers.massive import Massive
from app.providers.sec import SEC
from app.providers.x import XProvider
from pydantic import BaseModel


async def main():
    from fastmcp.client.transports import StreamableHttpTransport
    from langchain.mcp import MCPAdapter
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    http = ProviderHTTP()
    report = {}

    async def check(name, fn):
        try:
            details = await fn()
            report[name] = {"ok": True, **details}
        except Exception as error:
            report[name] = {
                "ok": False,
                "error_type": type(error).__name__,
                "code": getattr(error, "code", None),
                "http_status": getattr(error, "http_status", getattr(error, "status_code", None)),
            }
        print(name, json.dumps(report[name], ensure_ascii=False), flush=True)

    async def model():
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.dashscope_api_key.get_secret_value(),
            base_url=settings.dashscope_base_url,
            max_tokens=100,
            temperature=0,
            extra_body={"enable_thinking": False},
            max_retries=0,
        )

        class MathResult(BaseModel):
            answer: int

        structured = await llm.with_structured_output(MathResult, method="function_calling").ainvoke(
            "Return 2 + 2."
        )
        pieces = []
        async for chunk in llm.astream("Reply with OK only."):
            pieces.append(str(chunk.content))
        if structured.answer != 4 or not "".join(pieces):
            raise ValueError("Capability smoke failed")
        return {
            "model": settings.llm_model,
            "function_calling": True,
            "structured_output": True,
            "streaming": True,
        }

    async def massive():
        data = await Massive(http).quote("NVDA")
        return {
            "ticker": "NVDA",
            "price_type": data["data"]["price_type"],
            "as_of": data["data"]["as_of"],
            "available": data["available"],
        }

    async def sec():
        data = await SEC(http).filings("NVDA", "10-Q")
        return {"cik": data["company"]["cik"], "filings": len(data["data"])}

    async def x():
        provider = XProvider(http)
        user = await provider.user("NVIDIA")
        data = await provider.posts(user["id"], max_results=5)
        return {
            "username": user["username"],
            "posts_returned": len(data.get("data", [])),
            "pagination_available": bool(data.get("meta", {}).get("next_token")),
        }

    async def tavily():
        transport = StreamableHttpTransport(
            "https://mcp.tavily.com/mcp/",
            headers={"Authorization": "Bearer " + settings.tavily_api_key.get_secret_value()},
        )
        async with MCPAdapter(transport) as adapter:
            tool_list = await adapter.list_tools()
            catalog = [
                {"name": t.name, "schema": t.args_schema}
                for t in tool_list
                if "search" in t.name or "extract" in t.name
            ]
            (ROOT / ".runtime" / "tavily-catalog.json").write_text(
                json.dumps(catalog, default=str, indent=2), encoding="utf-8"
            )
            return {"tools": [t.name for t in tool_list], "transport": "streamable_http", "auth": "header"}

    for name, action in [
        ("dashscope", model),
        ("massive", massive),
        ("sec", sec),
        ("x", x),
        ("tavily", tavily),
    ]:
        await check(name, action)
    await http.close()
    (ROOT / ".runtime" / "provider-checks.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    from app.db import now, session_scope
    from app.models import ConfigEntry
    from sqlalchemy.dialects.postgresql import insert

    async with session_scope() as db:
        await db.execute(
            insert(ConfigEntry)
            .values(key="provider_health", value=report)
            .on_conflict_do_update(
                index_elements=[ConfigEntry.key], set_={"value": report, "updated_at": now()}
            )
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
