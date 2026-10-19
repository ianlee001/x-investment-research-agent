from fastapi import HTTPException
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.models import Claim, Message, Operation, Run, Thread
from app.services import ACTIVE


async def erase_runs(db: AsyncSession, runs: list[Run], checkpoint_ids: set[str]):
    """Delete graph state and business history in the same PostgreSQL transaction."""
    connection = await db.connection()
    raw = await connection.get_raw_connection()
    saver = AsyncPostgresSaver(raw.driver_connection)
    for checkpoint_id in checkpoint_ids:
        await saver.adelete_thread(checkpoint_id)
    run_ids = [run.id for run in runs]
    if not run_ids:
        return
    await db.execute(delete(Message).where(Message.run_id.in_(run_ids)))
    # Evidence refers to sources without ON DELETE CASCADE: delete its owning claims first.
    await db.execute(delete(Claim).where(Claim.run_id.in_(run_ids)))
    await db.execute(delete(Operation).where(func.split_part(Operation.key, ":", 1).in_(run_ids)))
    # Sources, approval rows and replay events cascade from the runs. Saved personal data is separate.
    await db.execute(delete(Run).where(Run.id.in_(run_ids)))


async def delete_research(run_id: str):
    async with session_scope() as db:
        run = await db.get(Run, run_id, with_for_update=True)
        if not run:
            raise HTTPException(404, "研究记录不存在")
        if run.kind not in {"research", "daily_brief"}:
            raise HTTPException(400, "请从研究对话入口删除整个对话")
        if run.status in ACTIVE:
            raise HTTPException(409, "请先停止任务，等待结束后再删除")
        await erase_runs(db, [run], {run.checkpoint_id or run.thread_id})
    return {"deleted": True}


async def delete_conversation(thread_id: str):
    async with session_scope() as db:
        # Busy runs may update Thread while finalizing. Reject them before taking the thread lock.
        if await db.scalar(select(Run.id).where(Run.thread_id == thread_id, Run.status.in_(ACTIVE))):
            raise HTTPException(409, "请先停止对话中的任务，等待结束后再删除")
        thread = await db.get(Thread, thread_id, with_for_update=True)
        if not thread:
            raise HTTPException(404, "对话不存在")
        # send_chat takes this same Thread lock before enqueuing a turn.
        runs = list(await db.scalars(select(Run).where(Run.thread_id == thread_id).with_for_update()))
        if any(run.status in ACTIVE for run in runs):
            raise HTTPException(409, "请先停止对话中的任务，等待结束后再删除")
        checkpoint_ids = {thread.id, thread.checkpoint_id} | {
            run.checkpoint_id or run.thread_id for run in runs
        }
        await erase_runs(db, runs, checkpoint_ids)
        await db.delete(thread)
    return {"deleted": True}
