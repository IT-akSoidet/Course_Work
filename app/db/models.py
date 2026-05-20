from datetime import date, datetime

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    address: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    rooms: Mapped[list["Room"]] = relationship(back_populates="building")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("building_id", "name", name="uq_rooms_building_name"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    building: Mapped["Building"] = relationship(back_populates="rooms")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")
    schedule_slots: Mapped[list["ScheduleSlot"]] = relationship(back_populates="room")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BIGINT, unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_bookings_starts_before_ends"),
        Index("idx_bookings_room_time", "room_id", "starts_at", "ends_at"),
        Index("idx_bookings_user_start", "user_id", "starts_at"),
        Index(
            "idx_bookings_active_room_time",
            "room_id",
            "starts_at",
            "ends_at",
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="bookings")
    room: Mapped["Room"] = relationship(back_populates="bookings")


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_schedule_starts_before_ends"),
        Index("idx_schedule_room_date", "room_id", "date"),
        Index("idx_schedule_room_time", "room_id", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(255), nullable=True)

    room: Mapped["Room"] = relationship(back_populates="schedule_slots")
