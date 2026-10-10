import ipaddress
import json
from urllib.parse import urlsplit

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage, ToolMessage

from app.config import get_settings
from app.db import session_scope
from app.models import Approval, Run
from app.providers.http import current_run
from app.services import BudgetExceeded, RunCancelled, capture_sources, event, increment_usage


def read_payload(message: ToolMessage) -> dict:
    if isinstance(message.artifact, dict) and isinstance(message.artifact.get("structured_content"), dict):
        payload = message.artifact["structured_content"]
        # Some MCP servers use a content envelope for structured results.
        if "results" in payload or "documents" in payload or "available" in payload:
            return payload
    content = message.content
    texts = (
        [content]
        if isinstance(content, str)
        else [
            item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
        ]
    )
    for text in texts:
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except (ValueError, TypeError):
            pass
    return {"text": "\n".join(texts)[:16000]}


def public_extract_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.port not in {None, 443}:
            return False
        if parts.hostname in {"localhost", "metadata.google.internal"} or "." not in parts.hostname:
            return False
        try:
            return ipaddress.ip_address(parts.hostname).is_global
        except ValueError:
            return not parts.hostname.endswith((".local", ".internal", ".localhost"))
    except ValueError:
        return False


class AuditBudgetMiddleware(AgentMiddleware):
    async def awrap_model_call(self, request, handler):
        context = request.runtime.context
        settings = get_settings()
        await increment_usage(context.run_id, "model_calls", 1, settings.max_model_calls)
        async with session_scope() as db:
            usage = dict((await db.get(Run, context.run_id)).usage)
        if usage.get("total_tokens", 0) >= settings.max_total_tokens:
            raise BudgetExceeded("已达到累计 Token 预算；现有证据已保存")
        # Keep whole user turns so assistant/tool pairs cannot be split by truncation.
        messages = request.messages
        human_positions = [i for i, m in enumerate(messages) if m.type == "human"]
        if len(human_positions) > 3:
            messages = messages[human_positions[-3] :]
        if sum(len(str(message.content)) for message in messages) > 150_000:
            raise BudgetExceeded("工具与对话内容超过本轮上下文预算，请缩小研究范围")
        overrides = {"messages": messages}
        if request.response_format is not None and (
            usage.get("model_calls", 0) > settings.max_research_rounds
            or usage.get("tool_calls", 0) >= 8
            or usage.get("total_tokens", 0) >= settings.max_total_tokens // 2
        ):
            # LangChain appends the ToolStrategy response tool after request.tools.
            # Removing read/write tools bounds exploration while preserving validated final output.
            overrides["tools"] = []
            overrides["system_message"] = SystemMessage(
                content=str(request.system_message.content)
                + "\n研究取证阶段已结束。立即使用 ReportDraft 输出已有来源支持的报告。缺失项目写入不确定性，不补造信息，不再扩大问题范围。"
            )
            await event(context.run_id, "stage_started", {"stage": "核对引用并生成报告"})
        response = await handler(request.override(**overrides))
        tokens = sum(
            (getattr(message, "usage_metadata", None) or {}).get("total_tokens", 0)
            for message in response.result
        )
        # Usage is actual billed response usage; record it even when one response crosses the soft cap.
        await increment_usage(context.run_id, "total_tokens", tokens)
        return response

    async def awrap_tool_call(self, request, handler):
        context = request.runtime.context
        settings = get_settings()
        name, args = request.tool_call["name"], dict(request.tool_call["args"])
        await increment_usage(context.run_id, "tool_calls", 1, settings.max_tool_calls)
        if name == "tavily_search":
            args.update(
                max_results=min(5, max(1, args.get("max_results", 5))),
                include_images=False,
                include_raw_content=False,
                search_depth="basic",
                topic="general",
            )
        elif name == "tavily_extract":
            urls = args.get("urls", [])
            if not urls or len(urls) > 3 or not all(public_extract_url(url) for url in urls):
                return ToolMessage(
                    content="Only 1-3 public HTTPS URLs are allowed.",
                    tool_call_id=request.tool_call["id"],
                    status="error",
                )
            args.update(include_images=False, extract_depth="basic")
        request = request.override(tool_call={**request.tool_call, "args": args})
        # The original URL/query is safe because only input schemas, not credentials, are model-visible.
        await event(context.run_id, "tool_started", {"tool": name, "args": args})
        if name.startswith("tavily_"):
            await increment_usage(context.run_id, "external_requests", 1, settings.max_external_requests)
        token = current_run.set(context.run_id)
        try:
            result = await handler(request)
        finally:
            current_run.reset(token)
        if not isinstance(result, ToolMessage):
            return result
        payload = read_payload(result)
        if result.status == "error":
            payload = {"available": False, "reason": "mcp_tool_error", "tool": name}
        if name in {
            "add_to_watchlist",
            "save_thesis",
            "update_investment_preferences",
            "update_source_trust",
        } and (result.status == "error" or payload.get("available") is False):
            from sqlalchemy import update

            async with session_scope() as db:
                await db.execute(
                    update(Approval)
                    .where(
                        Approval.run_id == context.run_id, Approval.tool_call_id == request.tool_call["id"]
                    )
                    .values(execution_status="failed")
                )
        if name.startswith("tavily_"):
            documents = []
            for row in payload.get("results", [])[:5]:
                url = row.get("url", "")
                documents.append(
                    {
                        "title": row.get("title") or url,
                        "url": url,
                        "excerpt": (row.get("raw_content") or row.get("content") or "")[:6000],
                        "published_at": row.get("published_date"),
                        "source_type": "sec"
                        if urlsplit(url).hostname in {"www.sec.gov", "sec.gov", "data.sec.gov"}
                        else "web",
                        "metadata": {
                            "retrieval": "search_snippet" if name == "tavily_search" else "page_extract"
                        },
                    }
                )
            payload = {
                "available": bool(documents),
                "provider": "tavily",
                "documents": documents,
                "failed_results": len(payload.get("failed_results", [])),
            }
        if "documents" in payload:
            # Cap BEFORE persistence so every quoted passage is exactly what the model received.
            remaining = 12000
            limited = []
            for document in payload["documents"][:6]:
                item = {**document, "excerpt": str(document.get("excerpt", ""))[: min(4000, remaining)]}
                remaining -= len(item["excerpt"])
                if item["excerpt"]:
                    limited.append(item)
            payload["documents"] = await capture_sources(
                context.run_id, limited, payload.get("provider", "unknown")
            )
            if len(json.dumps(payload.get("data", {}), ensure_ascii=False)) > 4000:
                payload["data"] = {"notice": "See bounded source excerpts; large duplicate payload omitted."}
        await event(
            context.run_id,
            "tool_completed",
            {
                "tool": name,
                "available": payload.get("available", result.status != "error"),
                "reason": payload.get("reason"),
                "sources": len(payload.get("documents", [])),
            },
        )
        if payload.get("available") is False:
            await increment_usage(context.run_id, "unavailable_tools", 1)
        result.content = json.dumps(payload, ensure_ascii=False, default=str)
        result.artifact = {"structured_content": payload}
        return result


def safe_tool_error(error, request):
    if isinstance(error, (BudgetExceeded, RunCancelled)):
        return None  # Do not swallow execution control signals.
    return json.dumps(
        {"available": False, "reason": "tool_execution_error", "error_type": type(error).__name__}
    )
