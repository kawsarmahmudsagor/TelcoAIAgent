"""remove condo property type

Revision ID: d255d68eb32a
Revises: 3d503a827127
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd255d68eb32a'
down_revision: Union[str, None] = '3d503a827127'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres enums can't drop a value in place -- recreate the type without
    # 'condo' and swap the column over. Existing condo rows become apartment
    # rather than being left dangling on a value the app no longer supports.
    op.execute("UPDATE properties SET property_type = 'apartment' WHERE property_type = 'condo'")
    op.execute("ALTER TYPE property_type RENAME TO property_type_old")
    op.execute("CREATE TYPE property_type AS ENUM ('apartment', 'house', 'townhouse', 'studio')")
    op.execute(
        "ALTER TABLE properties ALTER COLUMN property_type TYPE property_type "
        "USING property_type::text::property_type"
    )
    op.execute("DROP TYPE property_type_old")


def downgrade() -> None:
    op.execute("ALTER TYPE property_type RENAME TO property_type_old")
    op.execute("CREATE TYPE property_type AS ENUM ('apartment', 'condo', 'house', 'townhouse', 'studio')")
    op.execute(
        "ALTER TABLE properties ALTER COLUMN property_type TYPE property_type "
        "USING property_type::text::property_type"
    )
    op.execute("DROP TYPE property_type_old")
