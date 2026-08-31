"""create the initial application schema

Revision ID: 018f4a7dd030
Revises:
Create Date: 2026-07-09 05:33:26.879329
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "018f4a7dd030"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "empowerment_articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("sub_category", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("full_content", sa.Text(), nullable=True),
        sa.Column("difficulty_level", sa.String(length=50), nullable=True),
        sa.Column("estimated_read_time", sa.Integer(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("cover_image_url", sa.String(length=1000), nullable=True),
        sa.Column("video_url", sa.String(length=1000), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        op.f("ix_empowerment_articles_content_type"),
        "empowerment_articles",
        ["content_type"],
        unique=False,
    )
    op.create_table(
        "hackathons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("registration_start", sa.DateTime(), nullable=True),
        sa.Column("registration_end", sa.DateTime(), nullable=True),
        sa.Column("event_start", sa.DateTime(), nullable=True),
        sa.Column("event_end", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("UPCOMING", "REGISTERING", "ONGOING", "ENDED", name="hackathonstatus"),
            nullable=False,
        ),
        sa.Column(
            "mode",
            sa.Enum("ONLINE", "OFFLINE", "HYBRID", name="hackathonmode"),
            nullable=False,
        ),
        sa.Column("track_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("tech_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("prize_pool", sa.String(length=200), nullable=True),
        sa.Column("prize_pool_usd", sa.Float(), nullable=True),
        sa.Column("expected_participants", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_platform", sa.String(length=100), nullable=False),
        sa.Column("registration_url", sa.String(length=1000), nullable=True),
        sa.Column("organizer", sa.String(length=300), nullable=True),
        sa.Column("sponsors", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("external_click_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_hackathons_name"), "hackathons", ["name"], unique=False)
    op.create_index(op.f("ix_hackathons_status"), "hackathons", ["status"], unique=False)
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
        sa.Column("team_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cover_image_url", sa.String(length=1000), nullable=True),
        sa.Column("video_url", sa.String(length=1000), nullable=True),
        sa.Column("source_code_url", sa.String(length=1000), nullable=True),
        sa.Column("demo_url", sa.String(length=1000), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("bookmark_count", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "user_interactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("interaction_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_interactions_user_id"),
        "user_interactions",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("VISITOR", "DEVELOPER", "ADMIN", name="userrole"),
            nullable=False,
        ),
        sa.Column("profile_tags", sa.JSON(), nullable=True),
        sa.Column("edm_subscribed", sa.Boolean(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_user_interactions_user_id"), table_name="user_interactions")
    op.drop_table("user_interactions")
    op.drop_table("inspiration_items")
    op.drop_index(op.f("ix_hackathons_status"), table_name="hackathons")
    op.drop_index(op.f("ix_hackathons_name"), table_name="hackathons")
    op.drop_table("hackathons")
    op.drop_index(
        op.f("ix_empowerment_articles_content_type"),
        table_name="empowerment_articles",
    )
    op.drop_table("empowerment_articles")
