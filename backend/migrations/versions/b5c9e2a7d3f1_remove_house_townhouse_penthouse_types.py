"""remove house, townhouse and penthouse property types

Every home is an apartment (flat); a duplex stays its own type. Listings of the
removed types are re-typed first so no row is left holding a dropped value.

Revision ID: b5c9e2a7d3f1
Revises: a3d7e1f9c4b2
Create Date: 2026-10-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b5c9e2a7d3f1'
down_revision: Union[str, None] = 'a3d7e1f9c4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = "('apartment', 'studio', 'duplex', 'commercial', 'plot')"
_OLD = "('apartment', 'house', 'townhouse', 'studio', 'duplex', 'penthouse', 'commercial', 'plot')"


def _retype(values: str) -> None:
    op.execute("ALTER TYPE property_type RENAME TO property_type_old")
    op.execute(f"CREATE TYPE property_type AS ENUM {values}")
    op.execute(
        "ALTER TABLE properties ALTER COLUMN property_type TYPE property_type "
        "USING property_type::text::property_type"
    )
    op.execute("DROP TYPE property_type_old")


def upgrade() -> None:
    # Cast through text: the old values can't be named once they are gone.
    op.execute(
        "UPDATE properties SET property_type = 'apartment' "
        "WHERE property_type::text = 'house'"
    )
    op.execute(
        "UPDATE properties SET property_type = 'duplex' "
        "WHERE property_type::text IN ('townhouse', 'penthouse')"
    )
    # Client notes are free text: keep them to types that still exist.
    op.execute(
        "UPDATE clients SET preferred_property_type = 'apartment' "
        "WHERE preferred_property_type = 'house'"
    )
    op.execute(
        "UPDATE clients SET preferred_property_type = 'duplex' "
        "WHERE preferred_property_type IN ('townhouse', 'penthouse')"
    )
    _retype(_NEW)


def downgrade() -> None:
    # The re-typed rows stay apartments and duplexes; only the values come back.
    _retype(_OLD)
