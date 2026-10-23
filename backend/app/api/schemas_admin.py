"""Response shapes for /api/admin/* reads (documentation; bodies are built by app.bss.ops)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.bss.types import AccountSummary, CaseView, NotificationView, TransactionView
from app.models.telco import PlanType, SubscriberStatus


class SubscriberCounts(BaseModel):
    total: int
    prepaid: int
    postpaid: int


class RechargeToday(BaseModel):
    amount: Decimal
    count: int


class CaseCounts(BaseModel):
    open: int
    high_open: int


class AiCounts(BaseModel):
    chats_24h: int
    resolution_rate: float


class ActivityPoint(BaseModel):
    date: date
    recharge_amount: Decimal
    cases_created: int


class Health(BaseModel):
    recharge_success_rate_24h: float | None
    median_first_response_s: float | None
    active_incidents: int
    pending_transactions: int


class AttentionItem(BaseModel):
    kind: str
    title: str
    detail: str
    severity: str
    href: str


class Overview(BaseModel):
    subscribers: SubscriberCounts
    recharge_today: RechargeToday
    cases: CaseCounts
    ai: AiCounts
    activity: list[ActivityPoint]
    health: Health
    attention: list[AttentionItem]


class SubscriberItem(BaseModel):
    id: UUID
    full_name: str
    msisdn_masked: str
    plan_type: PlanType
    district: str
    status: SubscriberStatus
    main_balance: Decimal
    postpaid_due: Decimal
    joined_on: date


class SubscriberDetailHead(SubscriberItem):
    reward_points: int
    preferred_language: str


class SubscriberList(BaseModel):
    items: list[SubscriberItem]
    total: int


class SubscriberDetail(BaseModel):
    subscriber: SubscriberDetailHead
    summary: AccountSummary
    transactions: list[TransactionView]
    cases: list[CaseView]
    notifications: list[NotificationView]


class AdminTransaction(TransactionView):
    subscriber_name: str
    msisdn_masked: str


class TransactionList(BaseModel):
    items: list[AdminTransaction]
    total: int


class TransactionStats(BaseModel):
    volume: Decimal
    attempts: int
    success: int
    pending: int
    failed: int
    success_rate: float | None


class Intent(BaseModel):
    label: str
    count: int
    share: float


class MonitorMetrics(BaseModel):
    chats: int
    turns: int
    fallback_rate: float
    resolution_rate: float
    median_first_response_s: float | None
    p95_first_response_s: float | None
    intents: list[Intent]


class ReviewItem(BaseModel):
    conversation_id: UUID
    started_at: datetime
    subscriber_name: str | None
    no_tool_turns: int
    preview: str


class AuditItem(BaseModel):
    created_at: datetime
    actor: str
    action: str
    subscriber_name: str | None
    msisdn_masked: str | None
    detail: str


class AiMonitor(BaseModel):
    metrics: MonitorMetrics
    review_queue: list[ReviewItem]
    audit_trail: list[AuditItem]
