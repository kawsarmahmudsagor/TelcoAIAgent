"""voice: openrouter provider, elevenlabs_tts_model

Revision ID: c8e4f1a7d203
Revises: a91d4c7e2b58
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e4f1a7d203'
down_revision: Union[str, None] = 'a91d4c7e2b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE stt_tts_provider ADD VALUE IF NOT EXISTS 'openrouter'")
    op.add_column(
        'agent_config', sa.Column('elevenlabs_tts_model', sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('agent_config', 'elevenlabs_tts_model')
    # Postgres enums can't drop a value in place -- fold openrouter into
    # elevenlabs, then recreate the type without it and swap the column over.
    op.execute(
        "UPDATE agent_config SET stt_tts_provider = 'elevenlabs' "
        "WHERE stt_tts_provider = 'openrouter'"
    )
    op.execute("ALTER TYPE stt_tts_provider RENAME TO stt_tts_provider_old")
    op.execute("CREATE TYPE stt_tts_provider AS ENUM ('elevenlabs', 'deepgram')")
    op.execute(
        "ALTER TABLE agent_config ALTER COLUMN stt_tts_provider TYPE stt_tts_provider "
        "USING stt_tts_provider::text::stt_tts_provider"
    )
    op.execute("DROP TYPE stt_tts_provider_old")
