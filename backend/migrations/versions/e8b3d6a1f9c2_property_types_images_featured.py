"""add duplex/penthouse/commercial/plot property types, images, is_featured

Revision ID: e8b3d6a1f9c2
Revises: c5e19a7d3f42
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e8b3d6a1f9c2'
down_revision: Union[str, None] = 'c5e19a7d3f42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TYPES = ("duplex", "penthouse", "commercial", "plot")


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block.
    with op.get_context().autocommit_block():
        for value in _NEW_TYPES:
            op.execute(f"ALTER TYPE property_type ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        'properties',
        sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'properties',
        sa.Column('is_featured', sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('properties', 'is_featured')
    op.drop_column('properties', 'images')

    # Postgres enums can't drop a value in place -- fold the new types into the
    # closest old one, then recreate the type without them and swap the column over.
    op.execute(
        "UPDATE properties SET property_type = 'apartment' "
        "WHERE property_type IN ('duplex', 'penthouse')"
    )
    op.execute(
        "UPDATE properties SET property_type = 'house' "
        "WHERE property_type IN ('commercial', 'plot')"
    )
    op.execute("ALTER TYPE property_type RENAME TO property_type_old")
    op.execute("CREATE TYPE property_type AS ENUM ('apartment', 'house', 'townhouse', 'studio')")
    op.execute(
        "ALTER TABLE properties ALTER COLUMN property_type TYPE property_type "
        "USING property_type::text::property_type"
    )
    op.execute("DROP TYPE property_type_old")
