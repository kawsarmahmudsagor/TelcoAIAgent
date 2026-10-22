"""knowledge base: rag_sources, rag_source_pages, embedding_jobs, agent_config_rag_sources

Revision ID: a91d4c7e2b58
Revises: f3c7a2d9e514
Create Date: 2026-10-09 11:00:31.414168

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a91d4c7e2b58'
down_revision: Union[str, None] = 'f3c7a2d9e514'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rag_sources',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('content_type', sa.String(length=128), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('storage_path', sa.String(length=512), nullable=True),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('chroma_doc_id', sa.String(length=128), nullable=False),
    sa.Column('collection', sa.String(length=160), nullable=False),
    sa.Column('embedding_model', sa.String(length=128), nullable=False),
    sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('last_indexed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chroma_doc_id')
    )
    op.create_index(op.f('ix_rag_sources_source_type'), 'rag_sources', ['source_type'], unique=False)
    op.create_index(op.f('ix_rag_sources_status'), 'rag_sources', ['status'], unique=False)
    op.create_table('agent_config_rag_sources',
    sa.Column('agent_config_id', sa.UUID(), nullable=False),
    sa.Column('rag_source_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_config_id'], ['agent_config.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rag_source_id'], ['rag_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('agent_config_id', 'rag_source_id')
    )
    op.create_table('embedding_jobs',
    sa.Column('rag_source_id', sa.UUID(), nullable=True),
    sa.Column('job_type', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('priority', sa.Integer(), server_default='0', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['rag_source_id'], ['rag_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_embedding_jobs_rag_source_id'), 'embedding_jobs', ['rag_source_id'], unique=False)
    op.create_index('ix_embedding_jobs_status_priority_created', 'embedding_jobs', ['status', 'priority', 'created_at'], unique=False)
    op.create_table('rag_source_pages',
    sa.Column('rag_source_id', sa.UUID(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('normalized_url', sa.Text(), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=True),
    sa.Column('depth', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('chroma_doc_id', sa.String(length=128), nullable=False),
    sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['rag_source_id'], ['rag_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rag_source_id', 'normalized_url', name='uq_rag_source_page_url')
    )
    op.create_index(op.f('ix_rag_source_pages_chroma_doc_id'), 'rag_source_pages', ['chroma_doc_id'], unique=False)
    op.create_index(op.f('ix_rag_source_pages_rag_source_id'), 'rag_source_pages', ['rag_source_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_rag_source_pages_rag_source_id'), table_name='rag_source_pages')
    op.drop_index(op.f('ix_rag_source_pages_chroma_doc_id'), table_name='rag_source_pages')
    op.drop_table('rag_source_pages')
    op.drop_index('ix_embedding_jobs_status_priority_created', table_name='embedding_jobs')
    op.drop_index(op.f('ix_embedding_jobs_rag_source_id'), table_name='embedding_jobs')
    op.drop_table('embedding_jobs')
    op.drop_table('agent_config_rag_sources')
    op.drop_index(op.f('ix_rag_sources_status'), table_name='rag_sources')
    op.drop_index(op.f('ix_rag_sources_source_type'), table_name='rag_sources')
    op.drop_table('rag_sources')
