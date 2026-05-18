"""Initial schema for room booking bot.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False, unique=True),
    )
    op.create_table(
        "faculties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
    )
    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("address", sa.String(length=256), nullable=False),
    )
    op.create_table(
        "booking_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False, unique=True),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id"), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("building_id", "name", name="uq_rooms_building_name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("faculty_id", sa.Integer(), sa.ForeignKey("faculties.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("status_id", sa.Integer(), sa.ForeignKey("booking_statuses.id"), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("starts_at < ends_at", name="ck_bookings_starts_before_ends"),
    )
    op.create_index("idx_bookings_room_time", "bookings", ["room_id", "starts_at", "ends_at"])
    op.create_index("idx_bookings_user_start", "bookings", ["user_id", "starts_at"])
    op.execute(
        "CREATE INDEX idx_bookings_active_room_time ON bookings (room_id, starts_at, ends_at) "
        "WHERE status_id IN (1, 2)"
    )

    op.create_table(
        "room_unavailability",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="schedule"),
        sa.Column("source_external_id", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.CheckConstraint("starts_at < ends_at", name="ck_unavailability_starts_before_ends"),
    )
    op.create_index(
        "idx_unavailability_room_time", "room_unavailability", ["room_id", "starts_at", "ends_at"]
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_audit_actor_created", "audit_logs", ["actor_user_id", "created_at"])

    op.execute(
        """
        INSERT INTO roles (id, name) VALUES
        (1, 'student'),
        (2, 'teacher'),
        (3, 'admin');
        """
    )
    op.execute(
        """
        INSERT INTO booking_statuses (id, name) VALUES
        (1, 'pending'),
        (2, 'approved'),
        (3, 'rejected'),
        (4, 'cancelled');
        """
    )


def downgrade() -> None:
    op.drop_index("idx_audit_actor_created", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("idx_unavailability_room_time", table_name="room_unavailability")
    op.drop_table("room_unavailability")

    op.execute("DROP INDEX IF EXISTS idx_bookings_active_room_time")
    op.drop_index("idx_bookings_user_start", table_name="bookings")
    op.drop_index("idx_bookings_room_time", table_name="bookings")
    op.drop_table("bookings")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
    op.drop_table("rooms")
    op.drop_table("booking_statuses")
    op.drop_table("buildings")
    op.drop_table("faculties")
    op.drop_table("roles")
