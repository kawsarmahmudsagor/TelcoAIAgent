"""agent_config.greeting_followup (the greeting for a lead with a booked viewing)

Revision ID: a3d7e1f9c4b2
Revises: c8e1a4f7d2b5
Create Date: 2026-10-15 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3d7e1f9c4b2'
down_revision: Union[str, None] = 'c8e1a4f7d2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nothing copied from greeting_coldcall: that one is now for cold calls only.
    op.add_column('agent_config', sa.Column('greeting_followup', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_config', 'greeting_followup')
