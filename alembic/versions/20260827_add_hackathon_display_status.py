"""add LLM display screening status to hackathons

Revision ID: 20260827_display_status
Revises: ea71ab474944
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260827_display_status"
down_revision: str | None = "ea71ab474944"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


display_status_enum = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    name="hackathondisplaystatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    display_status_enum.create(bind, checkfirst=True)
    op.add_column(
        "hackathons",
        sa.Column(
            "display_status",
            display_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.create_index(
        "ix_hackathons_display_status",
        "hackathons",
        ["display_status"],
        unique=False,
    )
def downgrade() -> None:
    op.drop_index("ix_hackathons_display_status", table_name="hackathons")
    op.drop_column("hackathons", "display_status")
    display_status_enum.drop(op.get_bind(), checkfirst=True)
