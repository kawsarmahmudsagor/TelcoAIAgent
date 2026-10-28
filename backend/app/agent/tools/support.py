"""Support tools: case status, opening a case (after the customer confirms
it), and asking for a human agent (a high-priority case)."""

from __future__ import annotations

from uuid import uuid4

from livekit.agents import RunContext, function_tool

from app.agent.actions import CaseDraft
from app.agent.telco_format import format_day
from app.agent.tools._common import LISTED, listed, parse_enum, run_db, run_read, run_write
from app.agent.topics import ACCOUNT_CHANGED, CASE_CREATED, publish
from app.agent.userdata import SessionUserdata
from app.bss import cases
from app.models.telco import CasePriority, CaseSource


async def _publish_case(userdata: SessionUserdata, case) -> None:
    await publish(userdata, ACCOUNT_CHANGED, {"kind": "case", "ref": case.ref})
    await publish(
        userdata,
        CASE_CREATED,
        {
            "ref": case.ref,
            "category": case.category,
            "priority": case.priority.value,
            "status": case.status.value,
            "created_at": case.created_at.isoformat(),
        },
    )


async def run_get_case_status(userdata: SessionUserdata, ref: str | None = None) -> str:
    def build(db, sid):
        rows = cases.get_case_status(db, sid, ref=ref, limit=LISTED)
        if not rows:
            return "The customer has no support cases."
        total = len(rows) if ref else cases.count_cases(db, sid)
        lines = [f"{total} support case(s), open ones first:"]
        found = []
        for c in rows:
            line = (
                f"- {c.ref}: {c.category}, {c.status.value.replace('_', ' ')}, "
                f"opened {format_day(c.created_at)}, last update {format_day(c.updated_at)}"
            )
            if c.resolved_at:
                line += f", resolved {format_day(c.resolved_at)}"
            found.append(line + f". Issue: {c.description}")
        lines += listed(found, total)
        return "\n".join(lines)

    return await run_read(userdata, build, verify=True)


async def run_create_support_case(
    userdata: SessionUserdata,
    category: str,
    description: str,
    priority: str = "normal",
    confirmed: bool = False,
) -> str:
    async def call() -> str:
        draft = userdata.pending_case
        same = draft is not None and (draft.category, draft.description) == (category, description)
        if not confirmed or not same:
            userdata.pending_case = CaseDraft(
                action_id=uuid4(),
                category=category,
                description=description,
                priority=parse_enum(CasePriority, priority) or CasePriority.normal,
            )
            return (
                "Read back the category and description and ask the customer to confirm; "
                "then call again with confirmed=true."
            )
        sid = userdata.subscriber_id
        case = await run_db(
            lambda db: cases.create_case(
                db,
                sid,
                category=draft.category,
                description=draft.description,
                priority=draft.priority,
                source=CaseSource.agent,
                action_id=draft.action_id,
            )
        )
        userdata.pending_case = None
        await _publish_case(userdata, case)
        return (
            f"Opened support case {case.ref} ({case.priority.value} priority). "
            "Give them the case number."
        )

    return await run_write(userdata, call)


async def run_request_human_agent(userdata: SessionUserdata, reason: str) -> str:
    async def call() -> str:
        sid = userdata.subscriber_id
        if userdata.handoff_action_id is None:
            userdata.handoff_action_id = uuid4()
        action_id = userdata.handoff_action_id
        case = await run_db(
            lambda db: cases.request_human_agent(
                db, sid, reason=reason, source=CaseSource.agent, action_id=action_id
            )
        )
        await _publish_case(userdata, case)
        return (
            f"Opened high-priority case {case.ref}. "
            "A human agent will follow up on this case; there is no live transfer."
        )

    return await run_write(userdata, call)


@function_tool(name="get_case_status")
async def get_case_status(ctx: RunContext[SessionUserdata], ref: str | None = None) -> str:
    """Check the customer's support cases, unresolved ones first.

    Args:
        ref: Optional case number such as "TC-2048"; leave out to list their cases.
    """
    return await run_get_case_status(ctx.userdata, ref)


@function_tool(name="create_support_case")
async def create_support_case(
    ctx: RunContext[SessionUserdata],
    category: str,
    description: str,
    priority: str = "normal",
    confirmed: bool = False,
) -> str:
    """Open a support case for a problem the tools cannot fix. Call first with
    confirmed=false, read the details back, and call again with the same
    category and description and confirmed=true once the customer agrees.

    Args:
        category: Short snake_case label, e.g. "recharge_not_credited", "slow_data".
        description: One or two English sentences with the facts (amounts, times, references).
        priority: "normal" (default) or "high".
        confirmed: True only after the customer confirmed the read-back.
    """
    return await run_create_support_case(ctx.userdata, category, description, priority, confirmed)


@function_tool(name="request_human_agent")
async def request_human_agent(ctx: RunContext[SessionUserdata], reason: str) -> str:
    """Hand the customer to a human: opens a high-priority case for a human
    agent to follow up (there is no live transfer). Use when they ask for a
    person, are angry, or nothing else has worked.

    Args:
        reason: One English sentence on why, with the key facts.
    """
    return await run_request_human_agent(ctx.userdata, reason)
