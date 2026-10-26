"""agent_elevenlabs_stt: per-agent ElevenLabs STT model and language

Revision ID: c8f2a6d4e9b1
Revises: e5b9c3d72a14
Create Date: 2026-10-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8f2a6d4e9b1'
down_revision: Union[str, None] = 'e5b9c3d72a14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Null in both: the env default model, and auto-detected language.
    op.add_column('agent_config', sa.Column('elevenlabs_stt_model', sa.String(length=100), nullable=True))
    op.add_column('agent_config', sa.Column('elevenlabs_stt_language', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_config', 'elevenlabs_stt_language')
    op.drop_column('agent_config', 'elevenlabs_stt_model')
