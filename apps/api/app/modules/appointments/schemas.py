import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SettingsIn(BaseModel):
    enabled: bool | None = None
    timezone: str = "UTC"
    min_notice_minutes: int = Field(default=60, ge=0, le=10080)
    max_advance_days: int = Field(default=90, ge=1, le=730)
    cancellation_notice_minutes: int = Field(default=120, ge=0, le=10080)
    reschedule_notice_minutes: int = Field(default=120, ge=0, le=10080)


class SettingsOut(ORM, SettingsIn):
    id: uuid.UUID
    client_id: uuid.UUID


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    address: str = ""
    timezone: str = "UTC"
    is_active: bool = True


class LocationOut(ORM, LocationIn):
    id: uuid.UUID
    client_id: uuid.UUID
    created_at: datetime


class ProfessionalIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: EmailStr | None = None
    phone: str = ""
    location_ids: list[uuid.UUID] = []
    is_active: bool = True


class ProfessionalOut(ORM):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    email: str
    phone: str
    is_active: bool
    location_ids: list[uuid.UUID] = []
    created_at: datetime


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = ""
    duration_minutes: int = Field(default=60, ge=5, le=1440)
    buffer_before_minutes: int = Field(default=0, ge=0, le=1440)
    buffer_after_minutes: int = Field(default=0, ge=0, le=1440)
    is_active: bool = True


class ServiceOut(ORM, ServiceIn):
    id: uuid.UUID
    client_id: uuid.UUID
    created_at: datetime


class ProfessionalServiceIn(BaseModel):
    professional_id: uuid.UUID
    service_id: uuid.UUID
    location_id: uuid.UUID


class ScheduleIn(BaseModel):
    professional_id: uuid.UUID
    location_id: uuid.UUID
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: time, info):
        if info.data.get("start_time") and value <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return value


class ScheduleOut(ORM, ScheduleIn):
    id: uuid.UUID


class TimeOffIn(BaseModel):
    professional_id: uuid.UUID
    location_id: uuid.UUID | None = None
    kind: str = Field(default="block", pattern="^(vacation|block|exception)$")
    starts_at: datetime
    ends_at: datetime
    reason: str = ""


class TimeOffOut(ORM, TimeOffIn):
    id: uuid.UUID


class AppointmentCreate(BaseModel):
    location_id: uuid.UUID
    professional_id: uuid.UUID
    service_id: uuid.UUID
    starts_at: datetime
    customer_phone: str = Field(min_length=3, max_length=80)
    customer_name: str = Field(default="", max_length=180)
    customer_email: EmailStr | None = None
    notes: str = ""
    source: str = Field(default="portal", max_length=30)
    external_id: str | None = Field(default=None, max_length=180)


class AppointmentUpdate(BaseModel):
    starts_at: datetime | None = None
    location_id: uuid.UUID | None = None
    professional_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    customer_name: str | None = None
    customer_email: EmailStr | None = None
    notes: str | None = None
    status: str | None = Field(default=None, pattern="^(pending|confirmed|rescheduled|cancelled|completed|no_show)$")


class AppointmentOut(ORM):
    id: uuid.UUID
    client_id: uuid.UUID
    location_id: uuid.UUID
    professional_id: uuid.UUID
    service_id: uuid.UUID
    customer_phone: str
    customer_name: str
    customer_email: str
    notes: str
    source: str
    status: str
    starts_at: datetime
    ends_at: datetime
    external_id: str | None
    created_at: datetime
    updated_at: datetime


class AvailabilityQuery(BaseModel):
    service_id: uuid.UUID
    date_from: datetime
    date_to: datetime
    location_id: uuid.UUID | None = None
    professional_id: uuid.UUID | None = None
    slot_minutes: int = Field(default=30, ge=5, le=120)


class AvailabilitySlot(BaseModel):
    starts_at: datetime
    ends_at: datetime
    location_id: uuid.UUID
    professional_id: uuid.UUID
    service_id: uuid.UUID
