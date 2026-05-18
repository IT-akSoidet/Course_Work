from datetime import date as date_type
from datetime import datetime, time as time_type

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class Faculty(Base):
    __tablename__ = "faculties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="faculty")


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    address: Mapped[str] = mapped_column(String(256), nullable=False)

    rooms: Mapped[list["Room"]] = relationship(back_populates="building")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("building_id", "name", name="uq_rooms_building_name"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    building: Mapped["Building"] = relationship(back_populates="rooms")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")
    schedule_slots: Mapped[list["ScheduleSlot"]] = relationship(back_populates="room")
    unavailability: Mapped[list["RoomUnavailability"]] = relationship(back_populates="room")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BIGINT, unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    faculty_id: Mapped[int | None] = mapped_column(ForeignKey("faculties.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    role: Mapped["Role"] = relationship(back_populates="users")
    faculty: Mapped["Faculty"] = relationship(back_populates="users")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")


class BookingStatus(Base):
    __tablename__ = "booking_statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="status")


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
            postgresql_where=text("status_id IN (1, 2)"),
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("booking_statuses.id"), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="bookings")
    room: Mapped["Room"] = relationship(back_populates="bookings")
    status: Mapped["BookingStatus"] = relationship(back_populates="bookings")


class ScheduleSlot(Base):
    """Занятость аудитории по учебному расписанию (из CSV).

    Содержит конкретные пары с датой и временем.
    Аудитория считается занятой, если на запрошенный интервал
    есть пересечение с любым слотом этой таблицы.
    """

    __tablename__ = "schedule_slots"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_schedule_slots_starts_before_ends"),
        Index("idx_schedule_slots_room_time", "room_id", "starts_at", "ends_at"),
        Index("idx_schedule_slots_date", "room_id", "date"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    start_time: Mapped[time_type] = mapped_column(Time, nullable=False)
    end_time: Mapped[time_type] = mapped_column(Time, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    subject_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    teacher: Mapped[str | None] = mapped_column(String(256), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    room: Mapped["Room"] = relationship(back_populates="schedule_slots")


class RoomUnavailability(Base):
    """Занятость аудитории из внешних источников (Google Sheets, ручное закрытие).

    Используется при синхронизации с публичным расписанием ВШЭ.
    """

    __tablename__ = "room_unavailability"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_unavailability_starts_before_ends"),
        Index("idx_unavailability_room_time", "room_id", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="schedule")
    source_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    room: Mapped["Room"] = relationship(back_populates="unavailability")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_actor_created", "actor_user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
