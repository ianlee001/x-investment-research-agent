import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.approvals import decide
from app.config import ROOT, get_settings
from app.db import engine, now, session_scope, uid
from app.models import (
    Account,
    Approval,
    Claim,
    ConfigEntry,
    Message,
    Post,
    Run,
    RunEvent,
    Source,
    SourceProfile,
    Thread,
    WatchItem,
)
from app.providers.http import ProviderError, ProviderHTTP
from app.providers.massive import Massive
from app.providers.x import XProvider
from app.schemas import (
    AccountInput,
    AppPreferences,
    ChatInput,
    DecisionInput,
    ResearchInput,
    WatchInput,
    normalize_ticker,
)
from app.services import ACTIVE, TERMINAL, enqueue, preferences, public_row, save_preferences

settings = get_settings()


def validated_ticker(value: str) -> str:
    try:
        return normalize_ticker(value)
    except ValueError:
        raise HTTPException(422, "股票代码格式不正确") from None


@asynccontextmanager
async def lifespan(app):
    if (
        settings.app_host not in {"127.0.0.1", "localhost", "::1"}
        and not settings.app_auth_token.get_secret_value()
    ):
        raise RuntimeError("APP_AUTH_TOKEN is required when binding beyond loopback")
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(title="X Investment Research", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
)


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        auth = settings.app_auth_token.get_secret_value()
        if auth and not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + auth):
            return JSONResponse({"detail": "需要应用访问令牌"}, status_code=401)
        if not auth:
            if request.url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
                return JSONResponse({"detail": "仅允许本机访问"}, status_code=403)
            origin = request.headers.get("origin")
            allowed = {
                *settings.cors_origins,
                f"http://127.0.0.1:{settings.app_port}",
                f"http://localhost:{settings.app_port}",
            }
            if origin and origin not in allowed:
                return JSONResponse({"detail": "不允许此来源访问本地应用"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(ProviderError)
async def provider_error(request, error: ProviderError):
    return JSONResponse({"detail": error.result()}, status_code=502)


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    return JSONResponse({"detail": "已有相同记录或该对话仍有任务在执行，请刷新后重试"}, status_code=409)


@app.get("/api/v1/health")
async def health():
    async with session_scope() as db:
        await db.execute(text("SELECT 1"))
        worker = await db.get(ConfigEntry, "worker")
    alive = bool(worker and worker.updated_at > now() - timedelta(seconds=20))
    return {
        "status": "ok",
        "database": "connected",
        "worker": "online" if alive else "offline",
        "providers_configured": settings.provider_status(),
        "model": settings.llm_model,
        "version": "1.0.0",
    }


@app.get("/api/v1/dashboard")
async def dashboard():
    async with session_scope() as db:
        counts = {
            "watchlist": await db.scalar(select(func.count()).select_from(WatchItem)),
            "accounts": await db.scalar(select(func.count()).select_from(Account)),
            "posts": await db.scalar(
                select(func.count())
                .select_from(Post)
                .where(Post.unavailable.is_(False), Post.checked_at >= now() - timedelta(hours=24))
            ),
            "pending_approvals": await db.scalar(
                select(func.count()).select_from(Approval).where(Approval.status == "pending")
            ),
            "reports": await db.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.kind.in_(["research", "daily_brief"]), Run.status.in_(["completed", "partial"]))
            ),
        }
        runs = list(
            await db.scalars(
                select(Run)
                .where(Run.kind.in_(["research", "daily_brief", "chat"]))
                .order_by(Run.created_at.desc())
                .limit(6)
            )
        )
        brief = await db.scalar(
            select(Run)
            .where(Run.kind == "daily_brief", Run.result.is_not(None))
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        signals = list(
            await db.scalars(select(Claim).where(Claim.status.in_(["contradicted", "conflicting"])).limit(5))
        )
    return {
        "counts": counts,
        "recent_runs": [run_summary(r) for r in runs],
        "daily_brief": public_row(brief) if brief else None,
        "signals": [public_row(c) for c in signals],
    }


def run_summary(run):
    row = public_row(run)
    result = row.pop("result") or {}
    row.pop("resume_payload", None)
    row["title"] = result.get("title") or run.question[:110]
    row["summary"] = result.get("summary", "")[:500]
    row["coverage"] = result.get("coverage")
    return row


@app.get("/api/v1/x/accounts")
async def list_accounts():
    async with session_scope() as db:
        accounts = list(await db.scalars(select(Account).order_by(Account.created_at)))
    return [public_row(a) for a in accounts]


@app.post("/api/v1/x/accounts", status_code=201)
async def add_account(body: AccountInput):
    http = ProviderHTTP()
    try:
        user = await XProvider(http).user(body.username)
    finally:
        await http.close()
    async with session_scope() as db:
        values = {
            key: user.get(key) for key in ("id", "username", "name", "description", "profile_image_url")
        }
        await db.execute(insert(Account).values(**values).on_conflict_do_nothing())
        row = await db.get(Account, user["id"])
    return public_row(row)


@app.delete("/api/v1/x/accounts/{account_id}")
async def delete_account(account_id: str):
    async with session_scope() as db:
        row = await db.get(Account, account_id)
        if row:
            await db.delete(row)
    return {"deleted": True}


@app.post("/api/v1/x/accounts/{account_id}/sync", status_code=202)
async def sync_account_api(account_id: str):
    async with session_scope() as db:
        account = await db.get(Account, account_id)
        if not account:
            raise HTTPException(404, "账号不存在")
        active = await db.scalar(
            select(Run).where(Run.thread_id == "sync:" + account_id, Run.status.in_(ACTIVE))
        )
    run = active or await enqueue(
        f"同步 @{account.username}", kind="sync", thread_id="sync:" + account_id, post_id=account_id
    )
    return run_summary(run)


@app.get("/api/v1/x/posts")
async def list_posts(
    ticker: str = "",
    account: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = select(Post).where(Post.unavailable.is_(False), Post.checked_at >= now() - timedelta(hours=24))
    if ticker:
        query = query.where(Post.tickers.contains([validated_ticker(ticker)]))
    if account:
        query = query.where((Post.author_id == account) | (Post.username.ilike(account.lstrip("@"))))
    try:
        if date_from:
            query = query.where(Post.created_at >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.where(Post.created_at < datetime.fromisoformat(date_to) + timedelta(days=1))
    except ValueError:
        raise HTTPException(422, "日期应为 YYYY-MM-DD") from None
    if status:
        query = query.where(Post.id.in_(select(Run.post_id).join(Claim).where(Claim.status == status)))
    async with session_scope() as db:
        rows = list(await db.scalars(query.order_by(Post.created_at.desc()).offset(offset).limit(limit)))
        ids = [r.id for r in rows]
        runs = (
            list(await db.scalars(select(Run).where(Run.post_id.in_(ids)).order_by(Run.created_at.desc())))
            if ids
            else []
        )
    latest = {}
    for run in runs:
        latest.setdefault(run.post_id, run_summary(run))
    return [{**public_row(row), "research": latest.get(row.id)} for row in rows]


@app.get("/api/v1/x/posts/{post_id}")
async def get_post(post_id: str):
    async with session_scope() as db:
        post = await db.get(Post, post_id)
        if not post or post.unavailable or post.checked_at < now() - timedelta(hours=24):
            raise HTTPException(404, "原帖不存在、已不可访问或需要重新同步")
    return public_row(post)


@app.post("/api/v1/x/posts/{post_id}/research", status_code=202)
async def research_post(post_id: str):
    post = await get_post(post_id)
    return run_summary(
        await enqueue(
            "核查此 X 帖子的关键投资断言，区分事实、预测与意见，并给出来源和不确定性。",
            post_id=post_id,
            ticker=post["tickers"][0] if post["tickers"] else None,
        )
    )


@app.get("/api/v1/x/accounts/{account_id}/profile")
async def source_profile(account_id: str):
    async with session_scope() as db:
        account = await db.get(Account, account_id)
        if not account:
            raise HTTPException(404, "账号不存在")
        counts = (
            await db.execute(
                select(Claim.status, func.count())
                .join(Run, Run.id == Claim.run_id)
                .join(Post, Post.id == Run.post_id)
                .where(Post.author_id == account_id)
                .group_by(Claim.status)
            )
        ).all()
        manual = await db.get(SourceProfile, account.username.lower())
    return {
        "account": public_row(account),
        "claim_counts": dict(counts),
        "manual_trust": public_row(manual) if manual else None,
        "note": "这是已研究样本的状态计数，不代表该账号总体准确率；同一断言重复研究可能计入多次。",
    }


@app.get("/api/v1/watchlist")
async def list_watchlist():
    async with session_scope() as db:
        return [
            public_row(item)
            for item in await db.scalars(select(WatchItem).order_by(WatchItem.created_at.desc()))
        ]


@app.post("/api/v1/watchlist", status_code=201)
async def add_watch(body: WatchInput):
    async with session_scope() as db:
        await db.execute(insert(WatchItem).values(**body.model_dump()).on_conflict_do_nothing())
        return public_row(await db.get(WatchItem, body.ticker))


@app.delete("/api/v1/watchlist/{ticker}")
async def delete_watch(ticker: str):
    async with session_scope() as db:
        row = await db.get(WatchItem, normalize_ticker(ticker))
        if row:
            await db.delete(row)
    return {"deleted": True}


@app.get("/api/v1/watchlist/{ticker}")
async def watch_detail(ticker: str):
    ticker = normalize_ticker(ticker)
    async with session_scope() as db:
        item = await db.get(WatchItem, ticker)
        if not item:
            raise HTTPException(404, "标的不在关注列表")
        reports = list(
            await db.scalars(
                select(Run)
                .where(Run.ticker == ticker, Run.result.is_not(None))
                .order_by(Run.created_at.desc())
                .limit(10)
            )
        )
    return {**public_row(item), "reports": [run_summary(r) for r in reports]}


@app.get("/api/v1/market/{ticker}/{kind}")
async def market_data(ticker: str, kind: str, start: str = "", end: str = ""):
    ticker = validated_ticker(ticker)
    http = ProviderHTTP()
    try:
        provider = Massive(http)
        if kind == "quote":
            return await provider.quote(ticker)
        if kind == "profile":
            return await provider.profile(ticker)
        if kind == "history":
            return await provider.history(
                ticker,
                start or (now().date() - timedelta(days=30)).isoformat(),
                end or now().date().isoformat(),
            )
        raise HTTPException(404, "不支持的市场数据类型")
    except ProviderError as error:
        return error.result()
    finally:
        await http.close()


@app.post("/api/v1/research/runs", status_code=202)
async def create_research(body: ResearchInput):
    return run_summary(await enqueue(**body.model_dump()))


@app.get("/api/v1/research/runs")
async def list_runs(
    kind: str = "", ticker: str = "", limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)
):
    query = select(Run)
    if kind:
        query = query.where(Run.kind == kind)
    else:
        query = query.where(Run.kind.in_(["research", "daily_brief"]))
    if ticker:
        query = query.where(Run.ticker == validated_ticker(ticker))
    async with session_scope() as db:
        rows = list(await db.scalars(query.order_by(Run.created_at.desc()).limit(limit).offset(offset)))
    return [run_summary(row) for row in rows]


@app.get("/api/v1/research/runs/{run_id}")
async def get_run(run_id: str):
    async with session_scope() as db:
        run = await db.get(Run, run_id)
        if not run:
            raise HTTPException(404, "任务不存在")
        approvals = list(
            await db.scalars(
                select(Approval)
                .where(Approval.run_id == run_id)
                .order_by(Approval.created_at, Approval.action_index)
            )
        )
        sources = list(await db.scalars(select(Source).where(Source.run_id == run_id)))
        events = list(
            await db.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.type != "assistant_delta")
                .order_by(RunEvent.id)
                .limit(200)
            )
        )
    row = public_row(run)
    row.pop("resume_payload", None)
    return {
        **row,
        "approvals": [public_row(a) for a in approvals],
        "sources": [public_row(s) for s in sources],
        "events": [public_row(e) for e in events],
    }


@app.post("/api/v1/research/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    from app.worker import set_terminal

    async with session_scope() as db:
        run = await db.get(Run, run_id, with_for_update=True)
        if not run:
            raise HTTPException(404, "任务不存在")
        was_running = run.status == "running"
        if run.status in TERMINAL:
            return {"status": run.status}
        run.cancel_requested = True
    if not was_running:
        await set_terminal(run_id, "cancelled")
    return {"status": "cancelling" if was_running else "cancelled"}


@app.get("/api/v1/research/runs/{run_id}/events")
async def run_events(
    run_id: str,
    request: Request,
    after: int = Query(0, ge=0),
    last_event_id: str | None = Header(default=None),
):
    async with session_scope() as db:
        if not await db.get(Run, run_id):
            raise HTTPException(404, "任务不存在")
    try:
        after = max(after, int(last_event_id or 0))
    except ValueError:
        raise HTTPException(400, "无效的事件游标") from None

    async def stream():
        cursor, heartbeats = after, 0
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            async with session_scope() as db:
                rows = list(
                    await db.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == run_id, RunEvent.id > cursor)
                        .order_by(RunEvent.id)
                        .limit(100)
                    )
                )
                run = await db.get(Run, run_id)
                finished = run.status in TERMINAL
            for row in rows:
                cursor = row.id
                yield f"id: {row.id}\nevent: {row.type}\ndata: {json.dumps(jsonable_encoder(public_row(row)), ensure_ascii=False)}\n\n"
            if finished and not rows:
                yield "event: stream_end\ndata: {}\n\n"
                break
            heartbeats += 1
            if heartbeats % 15 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/chat/threads", status_code=201)
async def create_thread():
    async with session_scope() as db:
        thread = Thread()
        db.add(thread)
        await db.flush()
        return public_row(thread)


@app.get("/api/v1/chat/threads")
async def list_threads(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    async with session_scope() as db:
        return [
            public_row(t)
            for t in await db.scalars(
                select(Thread).order_by(Thread.updated_at.desc()).limit(limit).offset(offset)
            )
        ]


@app.get("/api/v1/chat/threads/{thread_id}")
async def get_thread(thread_id: str, limit: int = Query(50, ge=1, le=200), before: str = ""):
    async with session_scope() as db:
        thread = await db.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "对话不存在")
        query = select(Message).where(Message.thread_id == thread_id)
        if before:
            marker = await db.get(Message, before)
            if marker and marker.thread_id == thread_id:
                query = query.where(Message.created_at < marker.created_at)
        messages = list(await db.scalars(query.order_by(Message.created_at.desc()).limit(limit)))
        runs = list(
            await db.scalars(
                select(Run).where(Run.thread_id == thread_id).order_by(Run.created_at.desc()).limit(10)
            )
        )
    return {
        **public_row(thread),
        "messages": [public_row(m) for m in reversed(messages)],
        "runs": [run_summary(r) for r in runs],
        "next_before": messages[-1].id if len(messages) == limit else None,
    }


@app.post("/api/v1/chat/threads/{thread_id}/messages", status_code=202)
async def send_chat(thread_id: str, body: ChatInput):
    async with session_scope() as db:
        thread = await db.get(Thread, thread_id, with_for_update=True)
        if not thread:
            raise HTTPException(404, "对话不存在")
        if body.request_key:
            previous = await db.scalar(select(Run).where(Run.request_key == body.request_key))
            if previous:
                if previous.thread_id != thread_id or previous.question != body.content:
                    raise HTTPException(409, "幂等键已用于另一个请求")
                return run_summary(previous)
        active = await db.scalar(select(Run).where(Run.thread_id == thread_id, Run.status.in_(ACTIVE)))
        if active:
            raise HTTPException(409, "此对话仍有任务在执行或等待审批，请先处理")
        run = Run(
            id=uid(),
            thread_id=thread_id,
            checkpoint_id=thread.checkpoint_id,
            kind="chat",
            question=body.content,
            request_key=body.request_key or uid(),
        )
        db.add(run)
        await db.flush()
        db.add(Message(thread_id=thread_id, run_id=run.id, role="user", content=body.content))
        db.add(RunEvent(run_id=run.id, type="run_queued", data={"kind": "chat"}))
        if thread.title == "新的研究对话":
            thread.title = body.content[:70]
        thread.updated_at = now()
        return run_summary(run)


@app.get("/api/v1/approvals")
async def list_approvals(status: str = "", limit: int = Query(50, ge=1, le=100)):
    query = select(Approval)
    if status:
        query = query.where(Approval.status == status)
    async with session_scope() as db:
        return [
            public_row(a)
            for a in await db.scalars(
                query.order_by(Approval.created_at.desc(), Approval.action_index).limit(limit)
            )
        ]


@app.get("/api/v1/approvals/{approval_id}")
async def get_approval(approval_id: str):
    async with session_scope() as db:
        row = await db.get(Approval, approval_id)
        if not row:
            raise HTTPException(404, "审批不存在")
        return public_row(row)


@app.post("/api/v1/approvals/{approval_id}/{action}")
async def handle_approval(approval_id: str, action: str, body: DecisionInput):
    return await decide(approval_id, action, body)


@app.get("/api/v1/settings")
async def read_settings():
    async with session_scope() as db:
        status = await db.get(ConfigEntry, "provider_health")
    return {
        "preferences": (await preferences()).model_dump(),
        "providers": settings.provider_status(),
        "provider_health": status.value if status else {},
        "llm_model": settings.llm_model,
        "market_provider": "Massive",
        "market_data_type": "previous_session_close / adjusted daily bars",
        "limits": {
            "model_calls": settings.max_model_calls,
            "tool_calls": settings.max_tool_calls,
            "external_requests": settings.max_external_requests,
            "total_tokens": settings.max_total_tokens,
            "timeout_seconds": settings.run_timeout_seconds,
        },
        "x_search_enabled": settings.x_search_enabled,
    }


@app.put("/api/v1/settings")
async def update_settings(body: AppPreferences):
    await save_preferences(body)
    return body.model_dump()


@app.post("/api/v1/daily-brief", status_code=202)
async def generate_brief():
    items = await list_watchlist()
    if not items:
        raise HTTPException(400, "请先添加关注标的")
    selected = [item["ticker"] for item in items[:5]]
    return run_summary(
        await enqueue(
            f"为 {', '.join(selected)} 生成最近24小时的每日简报。注明证据、时间、冲突和待核查信息。最多覆盖5个标的。",
            kind="daily_brief",
        )
    )


dist = ROOT / "frontend" / "dist"
if (dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "接口不存在")
    if (dist / "index.html").exists():
        return FileResponse(dist / "index.html")
    return {
        "message": "Backend ready. Start frontend with npm run dev, or npm run build to serve it here.",
        "docs": "/docs",
    }
