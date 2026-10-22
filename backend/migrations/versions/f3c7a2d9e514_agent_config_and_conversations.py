"""agent_config singleton (replaces runtime_settings), conversations + messages

Revision ID: f3c7a2d9e514
Revises: e8b3d6a1f9c2
Create Date: 2026-10-09 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f3c7a2d9e514'
down_revision: Union[str, None] = 'e8b3d6a1f9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# runtime_settings created this type; reuse it rather than creating a new one.
_STT_TTS_PROVIDER = postgresql.ENUM('elevenlabs', 'deepgram', name='stt_tts_provider', create_type=False)


def upgrade() -> None:
    op.create_table(
        'agent_config',
        sa.Column('assistant_name', sa.String(length=100), nullable=True),
        sa.Column('agency_name', sa.String(length=255), nullable=True),
        sa.Column('prompt_identity_rules', sa.Text(), nullable=True),
        sa.Column('greeting_inbound', sa.Text(), nullable=True),
        sa.Column('greeting_coldcall', sa.Text(), nullable=True),
        sa.Column('llm_provider', sa.String(length=32), nullable=True),
        sa.Column('llm_model', sa.String(length=255), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('max_output_tokens', sa.Integer(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('stt_tts_provider', _STT_TTS_PROVIDER, nullable=True),
        sa.Column('deepgram_tts_model', sa.String(length=100), nullable=True),
        sa.Column('elevenlabs_voice_id', sa.String(length=100), nullable=True),
        sa.Column('rag_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('rag_top_k', sa.Integer(), server_default='5', nullable=False),
        sa.Column('rag_similarity_threshold', sa.Float(), server_default='0.45', nullable=False),
        sa.Column(
            'embedding_model',
            sa.String(length=128),
            server_default='google/gemini-embedding-2',
            nullable=False,
        ),
        sa.Column('chunk_size', sa.Integer(), server_default='512', nullable=False),
        sa.Column('chunk_overlap', sa.Integer(), server_default='50', nullable=False),
        sa.Column('embedding_migration_status', sa.String(length=16), nullable=True),
        sa.Column('embedding_migration_target', sa.String(length=128), nullable=True),
        sa.Column('embedding_migration_error', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # At most one row: a unique index on a constant.
    op.execute("CREATE UNIQUE INDEX uq_agent_config_singleton ON agent_config ((true))")
    # Always insert the singleton, so the API and the agent worker never race to
    # create it. Carries over the dashboard's voice provider if one was saved;
    # NULL otherwise, which falls back to STT_TTS_PROVIDER.
    op.execute(
        "INSERT INTO agent_config (id, stt_tts_provider) SELECT gen_random_uuid(), "
        "(SELECT stt_tts_provider FROM runtime_settings ORDER BY created_at LIMIT 1)"
    )
    op.drop_table('runtime_settings')

    op.create_table(
        'conversations',
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('room_name', sa.String(length=255), nullable=True),
        sa.Column('client_id', sa.UUID(), nullable=True),
        sa.Column('call_schedule_id', sa.UUID(), nullable=True),
        sa.Column('is_phone_call', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
        sa.Column('message_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['call_schedule_id'], ['call_schedule.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_conversations_channel'), 'conversations', ['channel'])
    op.create_index(op.f('ix_conversations_status'), 'conversations', ['status'])
    op.create_index(op.f('ix_conversations_started_at'), 'conversations', ['started_at'])

    op.create_table(
        'conversation_messages',
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=True),
        sa.Column('tool_args', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'seq', name='uq_conversation_message_seq'),
    )
    op.create_index(
        op.f('ix_conversation_messages_conversation_id'), 'conversation_messages', ['conversation_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_conversation_messages_conversation_id'), table_name='conversation_messages')
    op.drop_table('conversation_messages')
    op.drop_index(op.f('ix_conversations_started_at'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_status'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_channel'), table_name='conversations')
    op.drop_table('conversations')

    op.create_table(
        'runtime_settings',
        sa.Column('stt_tts_provider', _STT_TTS_PROVIDER, nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # Only an explicitly chosen provider; NULL meant "env default", which the old
    # get_or_create recreates on first read.
    op.execute(
        "INSERT INTO runtime_settings (id, stt_tts_provider) "
        "SELECT gen_random_uuid(), stt_tts_provider FROM agent_config "
        "WHERE stt_tts_provider IS NOT NULL LIMIT 1"
    )
    op.drop_table('agent_config')
