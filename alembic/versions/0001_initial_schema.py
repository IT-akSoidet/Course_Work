"""Minimal schema: buildings, rooms, users, bookings, schedule_slots.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("address", sa.String(length=256), nullable=False, server_default=""),
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("building_id", sa.Integer(), sa.ForeignKey("buildings.id"), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("building_id", "name", name="uq_rooms_building_name"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("starts_at < ends_at", name="ck_bookings_starts_before_ends"),
    )
    op.create_index("idx_bookings_room_time", "bookings", ["room_id", "starts_at", "ends_at"])
    op.create_index("idx_bookings_user_start", "bookings", ["user_id", "starts_at"])
    op.execute(
        "CREATE INDEX idx_bookings_active_room_time ON bookings "
        "(room_id, starts_at, ends_at) WHERE is_active = true"
    )

    op.create_table(
        "schedule_slots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("teacher", sa.String(length=255), nullable=True),
        sa.CheckConstraint("starts_at < ends_at", name="ck_schedule_starts_before_ends"),
    )
    op.create_index("idx_schedule_room_date", "schedule_slots", ["room_id", "date"])
    op.create_index(
        "idx_schedule_room_time", "schedule_slots", ["room_id", "starts_at", "ends_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_schedule_room_time", table_name="schedule_slots")
    op.drop_index("idx_schedule_room_date", table_name="schedule_slots")
    op.drop_table("schedule_slots")

    op.execute("DROP INDEX IF EXISTS idx_bookings_active_room_time")
    op.drop_index("idx_bookings_user_start", table_name="bookings")
    op.drop_index("idx_bookings_room_time", table_name="bookings")
    op.drop_table("bookings")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

    op.drop_table("rooms")
    op.drop_table("buildings")
