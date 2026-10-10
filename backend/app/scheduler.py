from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db import now, session_scope
from app.models import Account, Post, Run, WatchItem
from app.services import ACTIVE, enqueue, preferences


async def enqueue_syncs():
    prefs = await preferences()
    if not prefs.sync_enabled:
        return
    bucket = int(now().timestamp()) // (prefs.sync_interval_minutes * 60)
    async with session_scope() as db:
        accounts = list(await db.scalars(select(Account)))
    for account in accounts:
        async with session_scope() as db:
            if await db.scalar(
                select(Run.id).where(Run.thread_id == "sync:" + account.id, Run.status.in_(ACTIVE))
            ):
                continue
        await enqueue(
            f"同步 @{account.username}",
            kind="sync",
            thread_id="sync:" + account.id,
            post_id=account.id,
            request_key=f"sync:{account.id}:{bucket}",
        )


async def enqueue_brief():
    prefs = await preferences()
    if not prefs.daily_brief_enabled:
        return
    local_day = datetime.now(ZoneInfo(prefs.timezone)).date().isoformat()
    async with session_scope() as db:
        tickers = list(await db.scalars(select(WatchItem.ticker).order_by(WatchItem.ticker)))
    if not tickers:
        return
    # One bounded report per day; a broad watchlist is disclosed rather than silently overrunning budgets.
    chosen = tickers[:5]
    await enqueue(
        f"生成 {local_day} 每日投资研究简报。关注 {', '.join(chosen)}。只汇总最近24小时的重要变化，标注信息时间。"
        f"先读取本地 X 与关注列表，再按相关性查询新闻/财报/行情。关注列表共{len(tickers)}个标的，本次覆盖前5个。",
        kind="daily_brief",
        request_key="daily:" + local_day,
    )


async def enqueue_reconciliation():
    bucket = int(now().timestamp()) // 21600
    async with session_scope() as db:
        if await db.scalar(select(Run.id).where(Run.thread_id == "x-reconciliation", Run.status.in_(ACTIVE))):
            return
    await enqueue(
        "核对已保存 X 帖子的可见性",
        kind="reconcile",
        thread_id="x-reconciliation",
        request_key=f"reconcile:{bucket}",
    )


async def enqueue_auto_research():
    prefs = await preferences()
    if not prefs.auto_research_enabled or prefs.auto_research_max_per_day == 0:
        return
    day_start = datetime.now(ZoneInfo(prefs.timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
    async with session_scope() as db:
        existing = list(
            await db.scalars(
                select(Run.id).where(Run.request_key.like("auto:%"), Run.created_at >= day_start)
            )
        )
        tickers = list(await db.scalars(select(WatchItem.ticker)))
        posts = list(
            await db.scalars(
                select(Post)
                .where(Post.created_at >= now() - timedelta(hours=24), Post.unavailable.is_(False))
                .order_by(Post.created_at.desc())
                .limit(100)
            )
        )
    remaining = max(0, prefs.auto_research_max_per_day - len(existing))
    for post in posts:
        matching = sorted(set(post.tickers) & set(tickers))
        if not matching or remaining <= 0:
            continue
        async with session_scope() as db:
            previous = await db.scalar(select(Run.id).where(Run.request_key == "auto:" + post.id))
        if previous:
            continue
        await enqueue(
            "核查此 X 帖子中与关注标的有关的关键投资断言。",
            ticker=matching[0],
            post_id=post.id,
            request_key="auto:" + post.id,
        )
        remaining -= 1


async def create_scheduler():
    settings = get_settings()
    prefs = await preferences()
    scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=settings.sqlalchemy_url)},
        timezone=prefs.timezone,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    )
    scheduler.add_job(
        enqueue_syncs, "interval", minutes=prefs.sync_interval_minutes, id="x-sync", replace_existing=True
    )
    scheduler.add_job(
        enqueue_brief,
        "cron",
        hour=prefs.daily_brief_hour,
        minute=0,
        timezone=prefs.timezone,
        id="daily-brief",
        replace_existing=True,
    )
    scheduler.add_job(enqueue_reconciliation, "interval", hours=6, id="x-reconcile", replace_existing=True)
    scheduler.add_job(
        enqueue_auto_research, "interval", minutes=15, id="auto-research", replace_existing=True
    )
    scheduler.start()
    return scheduler
