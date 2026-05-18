"""Добавление таблицы schedule_slots для хранения расписания занятий из CSV.

Revision ID: 0002_add_schedule_slots
Revises: 0001_initial_schema
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_schedule_slots"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_slots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(length=256), nullable=True),
        sa.Column("subject_type", sa.String(length=128), nullable=True),
        sa.Column("teacher", sa.String(length=256), nullable=True),
        sa.Column("group_name", sa.String(length=64), nullable=True),
        sa.CheckConstraint("starts_at < ends_at", name="ck_schedule_slots_starts_before_ends"),
    )
    op.create_index(
        "idx_schedule_slots_room_time",
        "schedule_slots",
        ["room_id", "starts_at", "ends_at"],
    )
    op.create_index(
        "idx_schedule_slots_date",
        "schedule_slots",
        ["room_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("idx_schedule_slots_date", table_name="schedule_slots")
    op.drop_index("idx_schedule_slots_room_time", table_name="schedule_slots")
    op.drop_table("schedule_slots")
