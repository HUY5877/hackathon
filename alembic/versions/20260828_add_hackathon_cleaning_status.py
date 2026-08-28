"""add post-screening cleaning status to hackathons

Revision ID: 20260828_cleaning_status
Revises: 20260827_display_status
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260828_cleaning_status"
down_revision: str | None = "20260827_display_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hackathons",
        sa.Column(
            "is_cleaned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_hackathons_display_status_is_cleaned",
        "hackathons",
        ["display_status", "is_cleaned"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hackathons_display_status_is_cleaned",
        table_name="hackathons",
    )
    op.drop_column("hackathons", "is_cleaned")
