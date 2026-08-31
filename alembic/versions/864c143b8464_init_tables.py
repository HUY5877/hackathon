"""add inspiration and interaction tables

Revision ID: 864c143b8464
Revises: 4b7907a73f0d
Create Date: 2026-07-08 15:14:13.593262
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "864c143b8464"
down_revision: Union[str, None] = "4b7907a73f0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspiration_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("full_content", sa.Text(), nullable=True),
        sa.Column("teaser", sa.String(length=500), nullable=True),
        sa.Column("source_hackathon_name", sa.String(length=300), nullable=True),
        sa.Column("source_hackathon_url", sa.String(length=1000), nullable=True),
        sa.Column("team_name", sa.String(length=200), nullable=True),
        sa.Column("prize_won", sa.String(length=200), nullable=True),
        sa.Column("category_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("tech_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("difficulty_level", sa.String(length=50), nullable=True),
        sa.Column("team_profile", sa.JSON(), nullable=True),
        sa.Column("cover_image_url", sa.String(length=1000), nullable=True),
        sa.Column("video_url", sa.String(length=1000), nullable=True),
        sa.Column("source_code_url", sa.String(length=1000), nullable=True),
        sa.Column("demo_url", sa.String(length=1000), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("bookmark_count", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "user_interactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("interaction_type", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_interactions_user_id"),
        "user_interactions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_interactions_user_id"),
        table_name="user_interactions",
    )
    op.drop_table("user_interactions")
    op.drop_table("inspiration_items")
