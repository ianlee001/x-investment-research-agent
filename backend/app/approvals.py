from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.agent.tools import SENSITIVE_SCHEMAS
from app.config import get_settings
from app.db import now, session_scope
from app.models import Approval, Run, RunEvent
from app.schemas import DecisionInput
from app.services import public_row


async def record_interrupts(run_id: str, snapshot):
    calls = []
    for message in reversed(snapshot.values.get("messages", [])):
        if getattr(message, "tool_calls", None):
            calls = [call for call in message.tool_calls if call["name"] in SENSITIVE_SCHEMAS]
            break
    interrupts = list(snapshot.interrupts)
    if not interrupts:
        interrupts = [interrupt for task in snapshot.tasks for interrupt in task.interrupts]
    async with session_scope() as db:
        for interrupt in interrupts:
            for index, action in enumerate(interrupt.value.get("action_requests", [])):
                values = {
                    "run_id": run_id,
                    "interrupt_id": interrupt.id,
                    "action_index": index,
                    "tool_call_id": calls[index]["id"] if index < len(calls) else "",
                    "tool_name": action["name"],
                    "args": action["args"],
                    "description": action.get("description", ""),
                    "expires_at": now() + timedelta(hours=get_settings().approval_ttl_hours),
                }
                await db.execute(insert(Approval).values(**values).on_conflict_do_nothing())
        run = await db.get(Run, run_id)
        run.status, run.stage, run.resume_payload = "awaiting_approval", "等待人工审批", None
        db.add(
            RunEvent(run_id=run_id, type="approval_required", data={"interrupts": [i.id for i in interrupts]})
        )


async def decide(approval_id: str, action: str, body: DecisionInput):
    if action not in {"approve", "edit", "reject"}:
        raise HTTPException(400, "不支持的审批动作")
    # Lock the run before its rows so simultaneous decisions on a batch serialize consistently.
    async with session_scope() as db:
        approval = await db.get(Approval, approval_id)
        if not approval:
            raise HTTPException(404, "审批不存在")
        run = await db.get(Run, approval.run_id, with_for_update=True)
        await db.refresh(approval)
        if action == "edit":
            if body.args is None:
                raise HTTPException(422, "编辑审批必须提供完整参数")
            try:
                args = SENSITIVE_SCHEMAS[approval.tool_name].model_validate(body.args).model_dump()
            except ValueError:
                raise HTTPException(422, "参数未通过工具 schema 校验") from None
            decision = {"type": "edit", "edited_action": {"name": approval.tool_name, "args": args}}
        elif action == "reject":
            decision = {"type": "reject", "message": body.reason or "用户拒绝执行此操作。不要重试。"}
        else:
            decision = {"type": "approve"}
        if approval.status != "pending":
            if approval.decision == decision:
                return public_row(approval)  # Duplicate delivery is idempotent.
            raise HTTPException(409, "此审批已经处理；请刷新状态")
        if run.status != "awaiting_approval" or approval.expires_at <= now() or run.cancel_requested:
            raise HTTPException(409, "审批已失效或任务已取消")
        approval.decision, approval.decided_at = decision, now()
        approval.status = {"approve": "approved", "edit": "edited", "reject": "rejected"}[action]
        if action == "reject":
            approval.execution_status = "not_executed"
        await db.flush()
        rows = list(
            await db.scalars(
                select(Approval)
                .where(Approval.run_id == run.id, Approval.interrupt_id == approval.interrupt_id)
                .order_by(Approval.action_index)
            )
        )
        if all(row.decision for row in rows):
            # Native LangGraph resume, addressed by interrupt ID and original action order.
            run.resume_payload = {approval.interrupt_id: {"decisions": [row.decision for row in rows]}}
            run.status, run.stage = "queued", "审批完成，等待恢复执行"
        db.add(
            RunEvent(
                run_id=run.id,
                type="approval_decided",
                data={"approval_id": approval.id, "status": approval.status},
            )
        )
        return public_row(approval)
