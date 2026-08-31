"""add hackathon cover image

Revision ID: 985154533421
Revises: ee36b569b59d
Create Date: 2026-08-04 07:50:32.901727
"""

from alembic import op
import sqlalchemy as sa


revision = "985154533421"
down_revision = "ee36b569b59d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hackathons",
        sa.Column("cover_image", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hackathons", "cover_image")
