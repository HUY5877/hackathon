"""sync hackathon crawler schema

Revision ID: 73bef1ff85a5
Revises: e81c2277eb63
Create Date: 2026-08-03 13:40:21.607408
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "73bef1ff85a5"
down_revision: Union[str, None] = "e81c2277eb63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hackathons",
        sa.Column("cover_image", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hackathons", "cover_image")
