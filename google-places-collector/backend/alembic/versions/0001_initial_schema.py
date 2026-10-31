"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("query", sa.String(length=400), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("location_text", sa.String(length=200), nullable=False),
        sa.Column("formatted_address", sa.String(length=400), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("radius_meters", sa.Integer(), nullable=True),
        sa.Column("keyword", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("search_mode", sa.String(length=16), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("field_mode", sa.String(length=16), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_searches_user_id_users", ondelete="CASCADE"),
    )
    op.create_index("ix_searches_user_id", "searches", ["user_id"], unique=False)
    op.create_index("ix_searches_created_at", "searches", ["created_at"], unique=False)

    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("google_place_id", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=500), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("business_status", sa.String(length=32), nullable=True),
        sa.Column("maps_uri", sa.String(length=500), nullable=True),
        sa.Column("types_json", sa.JSON(), nullable=True),
        sa.Column("opening_hours_json", sa.JSON(), nullable=True),
        sa.Column("raw_allowed_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("google_place_id", name="uq_places_google_place_id"),
    )
    op.create_index("ix_places_dedupe_key", "places", ["dedupe_key"], unique=False)

    op.create_table(
        "search_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], name="fk_search_results_place_id_places", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"], name="fk_search_results_search_id_searches", ondelete="CASCADE"),
        sa.UniqueConstraint("search_id", "place_id", name="uq_search_results_search_place"),
    )
    op.create_index("ix_search_results_search_id", "search_results", ["search_id"], unique=False)
    op.create_index("ix_search_results_place_id", "search_results", ["place_id"], unique=False)

    op.create_table(
        "saved_places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], name="fk_saved_places_place_id_places", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_saved_places_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "place_id", name="uq_saved_places_user_place"),
    )
    op.create_index("ix_saved_places_user_id", "saved_places", ["user_id"], unique=False)
    op.create_index("ix_saved_places_place_id", "saved_places", ["place_id"], unique=False)

    op.create_table(
        "exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("field_mode", sa.String(length=16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"], name="fk_exports_search_id_searches", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_exports_user_id_users", ondelete="CASCADE"),
    )
    op.create_index("ix_exports_user_id", "exports", ["user_id"], unique=False)
    op.create_index("ix_exports_search_id", "exports", ["search_id"], unique=False)

    op.create_table(
        "api_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("search_type", sa.String(length=32), nullable=False),
        sa.Column("google_operation", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_api_usage_user_id_users", ondelete="SET NULL"),
    )
    op.create_index("ix_api_usage_user_id", "api_usage", ["user_id"], unique=False)
    op.create_index("ix_api_usage_created_at", "api_usage", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("api_usage")
    op.drop_table("exports")
    op.drop_table("saved_places")
    op.drop_table("search_results")
    op.drop_table("places")
    op.drop_table("searches")
    op.drop_table("users")
