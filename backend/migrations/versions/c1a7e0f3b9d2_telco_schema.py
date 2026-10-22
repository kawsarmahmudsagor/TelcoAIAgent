"""telco schema: drop the real-estate tables, add the telco BSS tables

Drops properties, clients, bookings, the call schedule, meeting invites and
offers with their enum types; removes the "properties" knowledge-base source and
its sync jobs; links conversations to a subscriber instead of a client; creates
the telco tables, enums and the TXN / TC reference sequences.

One-way: the dropped tables held demo data only.

Revision ID: c1a7e0f3b9d2
Revises: b5c9e2a7d3f1
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c1a7e0f3b9d2'
down_revision: Union[str, None] = 'b5c9e2a7d3f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REAL_ESTATE_TABLES = (
    "offer_properties",
    "offers",
    "meeting_invites",
    "bookings",
    "call_schedule",
    "properties",
    "clients",
)
_REAL_ESTATE_ENUMS = (
    "offer_type",
    "invite_status",
    "recipient_type",
    "booking_status",
    "booking_channel",
    "call_status",
    "property_type",
    "listing_type",
    "lead_status",
    "rent_or_buy",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    ]


def _subscriber_fk(nullable: bool = False) -> list:
    return [
        sa.Column('subscriber_id', sa.UUID(), nullable=nullable),
        sa.ForeignKeyConstraint(['subscriber_id'], ['subscribers.id'], ondelete='CASCADE'),
    ]


def _drop_real_estate() -> None:
    # conversations points at clients and call_schedule; those links go first.
    op.drop_constraint('conversations_client_id_fkey', 'conversations', type_='foreignkey')
    op.drop_constraint('conversations_call_schedule_id_fkey', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'client_id')
    op.drop_column('conversations', 'call_schedule_id')
    for table in _REAL_ESTATE_TABLES:
        op.drop_table(table)
    for enum_name in _REAL_ESTATE_ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")


def _drop_properties_source() -> None:
    # rag_sources.source_type and embedding_jobs.job_type are VARCHAR columns,
    # not Postgres enums, so removing the values is a row delete; the Python
    # enums (app.models.rag) drop `properties` / `sync_properties`.
    op.execute("DELETE FROM embedding_jobs WHERE job_type = 'sync_properties'")
    op.execute(
        "DELETE FROM embedding_jobs WHERE rag_source_id IN "
        "(SELECT id FROM rag_sources WHERE source_type = 'properties')"
    )
    op.execute("DELETE FROM rag_sources WHERE source_type = 'properties'")


def _create_telco() -> None:
    op.execute("CREATE SEQUENCE txn_ref_seq START WITH 840220")
    op.execute("CREATE SEQUENCE case_ref_seq START WITH 2049")

    op.create_table(
        'subscribers',
        sa.Column('msisdn', sa.String(length=11), nullable=False),
        sa.Column('full_name', sa.String(length=120), nullable=False),
        sa.Column('plan_type', sa.Enum('prepaid', 'postpaid', name='plan_type'), nullable=False),
        sa.Column('district', sa.String(length=60), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'suspended', name='subscriber_status'),
            server_default='active',
            nullable=False,
        ),
        sa.Column('joined_on', sa.Date(), nullable=False),
        sa.Column('reward_points', sa.Integer(), server_default='0', nullable=False),
        sa.Column('preferred_language', sa.String(length=2), server_default='bn', nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('msisdn'),
    )
    op.create_table(
        'balances',
        sa.Column('subscriber_id', sa.UUID(), nullable=False),
        sa.Column('main_balance', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
        sa.Column('postpaid_due', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['subscriber_id'], ['subscribers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('subscriber_id'),
    )
    op.create_table(
        'packages',
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.Enum('data', 'voice', 'bundle', 'sms', name='package_kind'), nullable=False),
        sa.Column('data_mb', sa.Integer(), server_default='0', nullable=False),
        sa.Column('minutes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('validity_days', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('tag', sa.String(length=32), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'subscriptions',
        *_subscriber_fk(),
        sa.Column('package_id', sa.UUID(), nullable=False),
        sa.Column('data_left_mb', sa.Integer(), nullable=False),
        sa.Column('minutes_left', sa.Integer(), nullable=False),
        sa.Column('sms_left', sa.Integer(), nullable=False),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('auto_renew', sa.Boolean(), server_default='false', nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'expired', name='subscription_status'),
            server_default='active',
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(['package_id'], ['packages.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_subscriptions_subscriber_status', 'subscriptions', ['subscriber_id', 'status'])
    op.create_table(
        'usage_events',
        *_subscriber_fk(),
        sa.Column('kind', sa.Enum('data', 'voice', 'sms', 'vas', name='usage_kind'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('unit', sa.String(length=8), nullable=False),
        sa.Column('charge', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
        sa.Column('description', sa.String(length=160), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_usage_events_subscriber_occurred', 'usage_events', ['subscriber_id', 'occurred_at']
    )
    op.create_table(
        'offers',
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('package_id', sa.UUID(), nullable=True),
        sa.Column('points_cost', sa.Integer(), nullable=True),
        sa.Column('cashback_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('cashback_cap', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('min_recharge', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            'audience',
            sa.Enum('all', 'prepaid', 'postpaid', name='offer_audience'),
            server_default='all',
            nullable=False,
        ),
        sa.Column('starts_on', sa.Date(), nullable=True),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(['package_id'], ['packages.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'transactions',
        sa.Column('ref', sa.String(length=16), nullable=False),
        *_subscriber_fk(),
        sa.Column('action_id', sa.UUID(), nullable=True),
        sa.Column('type', sa.Enum('recharge', 'purchase', 'redeem', name='txn_type'), nullable=False),
        sa.Column(
            'channel',
            sa.Enum('bkash', 'nagad', 'card', 'balance', 'points', name='txn_channel'),
            nullable=False,
        ),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('target_msisdn', sa.String(length=11), nullable=True),
        sa.Column('package_id', sa.UUID(), nullable=True),
        sa.Column('offer_id', sa.UUID(), nullable=True),
        sa.Column('cashback', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
        sa.Column(
            'status', sa.Enum('success', 'pending', 'failed', name='txn_status'), nullable=False
        ),
        sa.Column('failure_reason', sa.String(length=160), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['package_id'], ['packages.id']),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ref'),
        sa.UniqueConstraint('action_id'),
    )
    op.create_table(
        'support_cases',
        sa.Column('ref', sa.String(length=12), nullable=False),
        *_subscriber_fk(),
        sa.Column('action_id', sa.UUID(), nullable=True),
        sa.Column('category', sa.String(length=60), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'priority',
            sa.Enum('normal', 'high', name='case_priority'),
            server_default='normal',
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('open', 'in_review', 'resolved', name='case_status'),
            server_default='open',
            nullable=False,
        ),
        sa.Column(
            'source', sa.Enum('agent', 'portal', 'admin', name='case_source'), nullable=False
        ),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ref'),
        sa.UniqueConstraint('action_id'),
    )
    op.create_table(
        'network_incidents',
        sa.Column('district', sa.String(length=60), nullable=False),
        sa.Column('area', sa.String(length=120), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('outage', 'congestion', 'maintenance', name='incident_kind'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('investigating', 'scheduled', 'resolved', name='incident_status'),
            nullable=False,
        ),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'otp_challenges',
        *_subscriber_fk(),
        sa.Column('action_id', sa.UUID(), nullable=False),
        sa.Column('purpose', sa.String(length=32), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('action_id'),
    )
    op.create_table(
        'notifications',
        *_subscriber_fk(),
        sa.Column(
            'kind',
            sa.Enum('pack_expiring', 'low_balance', 'low_data', 'case_update', name='notification_kind'),
            nullable=False,
        ),
        sa.Column('subject_key', sa.String(length=80), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subscriber_id', 'kind', 'subject_key', name='uq_notification_subject'),
    )
    op.create_table(
        'audit_events',
        *_subscriber_fk(nullable=True),
        sa.Column(
            'actor',
            sa.Enum('agent', 'portal', 'admin', 'system', name='audit_actor'),
            nullable=False,
        ),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('action_id', sa.UUID(), nullable=True),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )

    op.add_column('conversations', sa.Column('subscriber_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'conversations_subscriber_id_fkey',
        'conversations',
        'subscribers',
        ['subscriber_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_conversations_subscriber_id'), 'conversations', ['subscriber_id'], unique=False
    )


def upgrade() -> None:
    _drop_real_estate()
    _drop_properties_source()
    _create_telco()


def downgrade() -> None:
    raise NotImplementedError("telco schema is one-way")
