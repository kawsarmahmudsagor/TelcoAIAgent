"""conversation visitor_id (the chat widget's recent conversations)

Revision ID: e2f9a4c7b6d1
Revises: d6a2b9e4c1f8
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e2f9a4c7b6d1'
down_revision: Union[str, None] = 'd6a2b9e4c1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('visitor_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f('ix_conversations_visitor_id'), 'conversations', ['visitor_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_conversations_visitor_id'), table_name='conversations')
    op.drop_column('conversations', 'visitor_id')
