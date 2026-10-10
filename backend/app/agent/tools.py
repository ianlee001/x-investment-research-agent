from langchain.tools import ToolRuntime, tool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.agent.context import RunContext
from app.db import now, session_scope
from app.models import Approval, Operation, Run, SourceProfile, WatchItem
from app.schemas import PreferenceInput, ThesisInput, TrustInput, WatchInput
from app.services import public_row

SENSITIVE_SCHEMAS = {
    "add_to_watchlist": WatchInput,
    "save_thesis": ThesisInput,
    "update_investment_preferences": PreferenceInput,
    "update_source_trust": TrustInput,
}


async def mutate(name: str, args: dict, runtime: ToolRuntime[RunContext]) -> dict:
    """Approval and mutation are linked by stable tool call ID; effects and audit commit together."""
    context = runtime.context
    key = f"{context.run_id}:{runtime.tool_call_id}"
    args = SENSITIVE_SCHEMAS[name].model_validate(args).model_dump()
    async with session_scope() as db:
        previous = await db.get(Operation, key)
        if previous:
            return previous.result
        approval = await db.scalar(
            select(Approval)
            .where(
                Approval.run_id == context.run_id,
                Approval.tool_call_id == runtime.tool_call_id,
                Approval.status.in_(["approved", "edited"]),
            )
            .with_for_update()
        )
        if not approval:
            raise ValueError("Missing committed human approval")
        expected = approval.decision.get("edited_action", {}).get("args", approval.args)
        if SENSITIVE_SCHEMAS[name].model_validate(expected).model_dump() != args:
            raise ValueError("Approved arguments do not match execution")
        if name == "add_to_watchlist":
            await db.execute(insert(WatchItem).values(**args).on_conflict_do_nothing())
        elif name == "save_thesis":
            item = await db.get(WatchItem, args["ticker"])
            if not item:
                raise ValueError("请先将标的加入关注列表，再保存研究观点")
            item.thesis = args["thesis"]
            # Upserting the same namespace/key is idempotent if a crash occurs before business commit.
            await runtime.store.aput(
                (context.user_id, "theses"), args["ticker"], {**args, "updated_at": now().isoformat()}
            )
        elif name == "update_investment_preferences":
            await runtime.store.aput((context.user_id, "preferences"), "investment", args)
        elif name == "update_source_trust":
            values = {
                "username": args["username"].lower(),
                "manual_trust": args["rating"],
                "rationale": args["reason"],
            }
            await db.execute(
                insert(SourceProfile)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[SourceProfile.username], set_={**values, "updated_at": now()}
                )
            )
            await runtime.store.aput((context.user_id, "source_trust"), values["username"], values)
        result = {"executed": True, "tool": name, "args": args, "approval_id": approval.id}
        approval.execution_status = "executed"
        db.add(Operation(key=key, result=result))
        return result


@tool
async def add_to_watchlist(
    ticker: str, runtime: ToolRuntime[RunContext], company_name: str = "", notes: str = ""
) -> dict:
    """Add a stock to the personal watchlist ONLY after explicit human approval in the UI."""
    return await mutate(
        "add_to_watchlist", {"ticker": ticker, "company_name": company_name, "notes": notes}, runtime
    )


@tool
async def save_thesis(ticker: str, thesis: str, runtime: ToolRuntime[RunContext]) -> dict:
    """Save a long-term investment thesis for an existing watchlist stock; human approval required."""
    return await mutate("save_thesis", {"ticker": ticker, "thesis": thesis}, runtime)


@tool
async def update_investment_preferences(
    risk_tolerance: str, investment_horizon: str, runtime: ToolRuntime[RunContext]
) -> dict:
    """Change long-term risk/horizon preferences, persisted across chat threads; requires human approval."""
    return await mutate(
        "update_investment_preferences",
        {"risk_tolerance": risk_tolerance, "investment_horizon": investment_horizon},
        runtime,
    )


@tool
async def update_source_trust(
    username: str, rating: str, reason: str, runtime: ToolRuntime[RunContext]
) -> dict:
    """Set a manual source trust label. It is distinct from evidence statistics and needs human approval."""
    return await mutate(
        "update_source_trust", {"username": username, "rating": rating, "reason": reason}, runtime
    )


@tool
async def get_research_context(runtime: ToolRuntime[RunContext]) -> dict:
    """Read watchlist, saved theses and investment preferences from PostgreSQL and long-term Store. No embeddings."""
    item = await runtime.store.aget((runtime.context.user_id, "preferences"), "investment")
    theses = await runtime.store.asearch((runtime.context.user_id, "theses"), limit=15)
    async with session_scope() as db:
        watchlist = list(await db.scalars(select(WatchItem).order_by(WatchItem.created_at.desc()).limit(50)))
    return {
        "preferences": item.value if item else {},
        "watchlist": [public_row(item) for item in watchlist],
        "theses": [{"ticker": item.key, "value": item.value} for item in theses],
    }


@tool
async def get_past_research(ticker: str, runtime: ToolRuntime[RunContext]) -> dict:
    """Look up the last five saved reports by exact ticker; historical conclusions are not fresh external evidence."""
    async with session_scope() as db:
        reports = list(
            await db.scalars(
                select(Run)
                .where(
                    Run.ticker == ticker.upper(), Run.result.is_not(None), Run.id != runtime.context.run_id
                )
                .order_by(Run.created_at.desc())
                .limit(5)
            )
        )
    return {
        "reports": [
            {
                "id": item.id,
                "created_at": item.created_at.isoformat(),
                "summary": (item.result or {}).get("summary", "")[:2500],
            }
            for item in reports
        ],
        "notice": "Historical conclusions require fresh verification.",
    }


READ_TOOLS = [get_research_context, get_past_research]
WRITE_TOOLS = [add_to_watchlist, save_thesis, update_investment_preferences, update_source_trust]
