"""store inspiration team profiles as JSONB

Revision ID: e81c2277eb63
Revises: 864c143b8464
Create Date: 2026-07-09 10:50:27.010584
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e81c2277eb63"
down_revision: Union[str, None] = "864c143b8464"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "inspiration_items",
        "team_profile",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "inspiration_items",
        "team_profile",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
    )
