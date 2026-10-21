"""add maintenance requests and lease documents

Revision ID: 0b4d9a7f2e61
Revises: 8f93c2a1d640
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "0b4d9a7f2e61"
down_revision = "8f93c2a1d640"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=5000), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="submitted",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('submitted', 'in_progress', 'resolved', 'closed')",
            name="ck_maintenance_requests_status",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_maintenance_requests_lease_id"),
        "maintenance_requests",
        ["lease_id"],
        unique=False,
    )
    op.create_table(
        "maintenance_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["maintenance_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_maintenance_photos_request_id"),
        "maintenance_photos",
        ["request_id"],
        unique=False,
    )
    op.create_table(
        "lease_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=180), nullable=False),
        sa.Column("object_key", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_lease_documents_lease_id"),
        "lease_documents",
        ["lease_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_lease_documents_lease_id"), table_name="lease_documents")
    op.drop_table("lease_documents")
    op.drop_index(op.f("ix_maintenance_photos_request_id"), table_name="maintenance_photos")
    op.drop_table("maintenance_photos")
    op.drop_index(op.f("ix_maintenance_requests_lease_id"), table_name="maintenance_requests")
    op.drop_table("maintenance_requests")
