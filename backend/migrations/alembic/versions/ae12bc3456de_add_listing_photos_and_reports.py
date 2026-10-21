"""Add listing photos and reports.

Revision ID: ae12bc3456de
Revises: c38f1a20d7b4
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "ae12bc3456de"
down_revision = "c38f1a20d7b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "property_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("property_id", sa.Integer(), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("object_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column(
            "is_cover",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(property_id IS NOT NULL AND unit_id IS NULL) OR "
            "(property_id IS NULL AND unit_id IS NOT NULL)",
            name="ck_property_photos_single_listing",
        ),
        sa.CheckConstraint(
            "room_id IS NULL OR unit_id IS NOT NULL",
            name="ck_property_photos_room_requires_unit",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_property_photos_property_id", "property_photos", ["property_id"]
    )
    op.create_index("ix_property_photos_unit_id", "property_photos", ["unit_id"])
    op.create_index("ix_property_photos_room_id", "property_photos", ["room_id"])
    op.create_index(
        "uq_property_photos_property_cover",
        "property_photos",
        ["property_id"],
        unique=True,
        sqlite_where=sa.text("is_cover = 1 AND property_id IS NOT NULL"),
        postgresql_where=sa.text("is_cover IS TRUE AND property_id IS NOT NULL"),
    )
    op.create_index(
        "uq_property_photos_unit_cover",
        "property_photos",
        ["unit_id"],
        unique=True,
        sqlite_where=sa.text("is_cover = 1 AND unit_id IS NOT NULL"),
        postgresql_where=sa.text("is_cover IS TRUE AND unit_id IS NOT NULL"),
    )
    op.create_table(
        "listing_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("details", sa.String(length=1000), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(property_id IS NOT NULL AND unit_id IS NULL) OR "
            "(property_id IS NULL AND unit_id IS NOT NULL)",
            name="ck_listing_reports_single_listing",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_listing_reports_user_id", "listing_reports", ["user_id"])
    op.create_index("ix_listing_reports_property_id", "listing_reports", ["property_id"])
    op.create_index("ix_listing_reports_unit_id", "listing_reports", ["unit_id"])


def downgrade():
    op.drop_index("ix_listing_reports_unit_id", table_name="listing_reports")
    op.drop_index("ix_listing_reports_property_id", table_name="listing_reports")
    op.drop_index("ix_listing_reports_user_id", table_name="listing_reports")
    op.drop_table("listing_reports")
    op.drop_index(
        "uq_property_photos_unit_cover", table_name="property_photos"
    )
    op.drop_index(
        "uq_property_photos_property_cover", table_name="property_photos"
    )
    op.drop_index("ix_property_photos_room_id", table_name="property_photos")
    op.drop_index("ix_property_photos_unit_id", table_name="property_photos")
    op.drop_index("ix_property_photos_property_id", table_name="property_photos")
    op.drop_table("property_photos")
