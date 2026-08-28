import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base
from ...models import new_uuid, now_utc


class AppointmentSettings(Base):
    __tablename__ = "appointments_settings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    min_notice_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    max_advance_days: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    cancellation_notice_minutes: Mapped[int] = mapped_column(Integer, default=120, server_default="120")
    reschedule_notice_minutes: Mapped[int] = mapped_column(Integer, default=120, server_default="120")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class AppointmentLocation(Base):
    __tablename__ = "appointments_locations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    address: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AppointmentProfessional(Base):
    __tablename__ = "appointments_professionals"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProfessionalLocation(Base):
    __tablename__ = "appointments_professional_locations"
    __table_args__ = (UniqueConstraint("professional_id", "location_id", name="uq_appointments_professional_location"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    professional_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_professionals.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_locations.id", ondelete="CASCADE"), index=True)


class AppointmentService(Base):
    __tablename__ = "appointments_services"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    buffer_before_minutes: Mapped[int] = mapped_column(Integer, default=0)
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProfessionalService(Base):
    __tablename__ = "appointments_professional_services"
    __table_args__ = (UniqueConstraint("professional_id", "service_id", "location_id", name="uq_appointments_professional_service_location"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    professional_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_professionals.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_services.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_locations.id", ondelete="CASCADE"), index=True)


class ProfessionalSchedule(Base):
    __tablename__ = "appointments_schedules"
    __table_args__ = (UniqueConstraint("professional_id", "location_id", "weekday", "start_time", name="uq_appointments_schedule_start"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    professional_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_professionals.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_locations.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[object] = mapped_column(Time)
    end_time: Mapped[object] = mapped_column(Time)


class AppointmentTimeOff(Base):
    __tablename__ = "appointments_time_off"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    professional_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_professionals.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("appointments_locations.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="block")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, default="")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("client_id", "external_id", name="uq_appointments_external_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_locations.id", ondelete="RESTRICT"), index=True)
    professional_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_professionals.id", ondelete="RESTRICT"), index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments_services.id", ondelete="RESTRICT"), index=True)
    customer_phone: Mapped[str] = mapped_column(String(80), index=True)
    customer_name: Mapped[str] = mapped_column(String(180), default="")
    customer_email: Mapped[str] = mapped_column(String(320), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(30), default="portal")
    status: Mapped[str] = mapped_column(String(30), default="confirmed", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    external_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
