"""agent_config: operator_* fields and greeting_nudge; drop cold-call greetings

Revision ID: d4e8a1c2f7b3
Revises: c1a7e0f3b9d2
Create Date: 2026-10-22 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e8a1c2f7b3'
down_revision: Union[str, None] = 'c1a7e0f3b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RENAMES = (
    ("agency_name", "operator_name"),
    ("agency_phone", "operator_phone"),
    ("agency_address", "operator_address"),
)


def upgrade() -> None:
    for old, new in _RENAMES:
        op.alter_column("agent_config", old, new_column_name=new)
    op.add_column("agent_config", sa.Column("greeting_nudge", sa.Text(), nullable=True))
    op.drop_column("agent_config", "greeting_coldcall")
    op.drop_column("agent_config", "greeting_followup")
    op.execute(
        "UPDATE agent_config SET "
        "prompt_identity_rules = replace(prompt_identity_rules, '{agency_name}', '{operator_name}'), "
        "greeting_inbound = replace(greeting_inbound, '{agency_name}', '{operator_name}')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agent_config SET "
        "prompt_identity_rules = replace(prompt_identity_rules, '{operator_name}', '{agency_name}'), "
        "greeting_inbound = replace(greeting_inbound, '{operator_name}', '{agency_name}')"
    )
    op.add_column("agent_config", sa.Column("greeting_followup", sa.Text(), nullable=True))
    op.add_column("agent_config", sa.Column("greeting_coldcall", sa.Text(), nullable=True))
    op.drop_column("agent_config", "greeting_nudge")
    for old, new in _RENAMES:
        op.alter_column("agent_config", new, new_column_name=old)
