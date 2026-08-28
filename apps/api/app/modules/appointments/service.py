import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import (
    Appointment, AppointmentLocation, AppointmentProfessional, AppointmentService,
    AppointmentSettings, AppointmentTimeOff, ProfessionalLocation, ProfessionalSchedule,
    ProfessionalService,
)

ACTIVE_STATUSES = ("pending", "confirmed", "rescheduled")


def get_settings(db: Session, client_id: uuid.UUID, *, create: bool = True) -> AppointmentSettings | None:
    row = db.scalar(select(AppointmentSettings).where(AppointmentSettings.client_id == client_id))
    if not row and create:
        row = AppointmentSettings(client_id=client_id)
        db.add(row)
        db.flush()
    return row


def ensure_enabled(db: Session, client_id: uuid.UUID) -> AppointmentSettings:
    settings = get_settings(db, client_id)
    if not settings or not settings.enabled:
        raise HTTPException(status_code=403, detail="Appointments are not enabled for this client")
    return settings


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {name}") from exc


def as_utc(value: datetime, tz: ZoneInfo | None = None) -> datetime:
    current = value.replace(tzinfo=tz) if value.tzinfo is None else value
    return current.astimezone(timezone.utc).replace(tzinfo=None)


def _validate_setup(db: Session, client_id: uuid.UUID, location_id: uuid.UUID, professional_id: uuid.UUID, service_id: uuid.UUID) -> tuple[AppointmentLocation, AppointmentProfessional, AppointmentService]:
    location = db.scalar(select(AppointmentLocation).where(AppointmentLocation.id == location_id, AppointmentLocation.client_id == client_id, AppointmentLocation.is_active.is_(True)))
    professional = db.scalar(select(AppointmentProfessional).where(AppointmentProfessional.id == professional_id, AppointmentProfessional.client_id == client_id, AppointmentProfessional.is_active.is_(True)))
    service = db.scalar(select(AppointmentService).where(AppointmentService.id == service_id, AppointmentService.client_id == client_id, AppointmentService.is_active.is_(True)))
    if not location or not professional or not service:
        raise HTTPException(status_code=422, detail="The location, professional or service is not available")
    linked = db.scalar(select(ProfessionalLocation.id).where(ProfessionalLocation.professional_id == professional_id, ProfessionalLocation.location_id == location_id))
    offered = db.scalar(select(ProfessionalService.id).where(ProfessionalService.professional_id == professional_id, ProfessionalService.service_id == service_id, ProfessionalService.location_id == location_id))
    if not linked or not offered:
        raise HTTPException(status_code=422, detail="That professional does not offer this service at this location")
    return location, professional, service


def _overlaps(db: Session, client_id: uuid.UUID, professional_id: uuid.UUID, starts: datetime, ends: datetime, exclude_id: uuid.UUID | None = None) -> bool:
    query = select(Appointment.id).where(
        Appointment.client_id == client_id,
        Appointment.professional_id == professional_id,
        Appointment.status.in_(ACTIVE_STATUSES),
        Appointment.starts_at < ends,
        Appointment.ends_at > starts,
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    return db.scalar(query) is not None


def slot_is_available(db: Session, client_id: uuid.UUID, location_id: uuid.UUID, professional_id: uuid.UUID, service_id: uuid.UUID, starts_at: datetime, *, exclude_id: uuid.UUID | None = None) -> tuple[datetime, datetime]:
    settings = ensure_enabled(db, client_id)
    location, _, service = _validate_setup(db, client_id, location_id, professional_id, service_id)
    tz = zone(location.timezone or settings.timezone)
    starts = as_utc(starts_at, tz)
    ends = starts + timedelta(minutes=service.duration_minutes)
    buffered_start = starts - timedelta(minutes=service.buffer_before_minutes)
    buffered_end = ends + timedelta(minutes=service.buffer_after_minutes)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if buffered_start < now + timedelta(minutes=settings.min_notice_minutes):
        raise HTTPException(status_code=422, detail="This appointment does not meet the minimum notice")
    if buffered_start > now + timedelta(days=settings.max_advance_days):
        raise HTTPException(status_code=422, detail="This appointment is too far in the future")
    local_start = starts.replace(tzinfo=timezone.utc).astimezone(tz)
    local_end = ends.replace(tzinfo=timezone.utc).astimezone(tz)
    schedule = db.scalar(select(ProfessionalSchedule).where(ProfessionalSchedule.professional_id == professional_id, ProfessionalSchedule.location_id == location_id, ProfessionalSchedule.weekday == local_start.weekday(), ProfessionalSchedule.start_time <= local_start.time(), ProfessionalSchedule.end_time >= local_end.time()))
    if not schedule:
        raise HTTPException(status_code=422, detail="The professional is not available at that time")
    blocked = db.scalar(select(AppointmentTimeOff.id).where(AppointmentTimeOff.professional_id == professional_id, AppointmentTimeOff.starts_at < buffered_end, AppointmentTimeOff.ends_at > buffered_start, (AppointmentTimeOff.location_id.is_(None) | (AppointmentTimeOff.location_id == location_id))))
    if blocked or _overlaps(db, client_id, professional_id, buffered_start, buffered_end, exclude_id):
        raise HTTPException(status_code=409, detail="That time is no longer available")
    return starts, ends


def available_slots(db: Session, client_id: uuid.UUID, service_id: uuid.UUID, date_from: datetime, date_to: datetime, *, location_id: uuid.UUID | None = None, professional_id: uuid.UUID | None = None, slot_minutes: int = 30) -> list[dict]:
    settings = ensure_enabled(db, client_id)
    service = db.scalar(select(AppointmentService).where(AppointmentService.id == service_id, AppointmentService.client_id == client_id, AppointmentService.is_active.is_(True)))
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    locations = db.scalars(select(AppointmentLocation).where(AppointmentLocation.client_id == client_id, AppointmentLocation.is_active.is_(True), *( [AppointmentLocation.id == location_id] if location_id else [] ))).all()
    professionals = db.scalars(select(AppointmentProfessional).where(AppointmentProfessional.client_id == client_id, AppointmentProfessional.is_active.is_(True), *( [AppointmentProfessional.id == professional_id] if professional_id else [] ))).all()
    start_date = date_from.date()
    end_date = date_to.date()
    results: list[dict] = []
    for location in locations:
        tz = zone(location.timezone or settings.timezone)
        for professional in professionals:
            linked = db.scalar(select(ProfessionalLocation.id).where(ProfessionalLocation.professional_id == professional.id, ProfessionalLocation.location_id == location.id))
            offered = db.scalar(select(ProfessionalService.id).where(ProfessionalService.professional_id == professional.id, ProfessionalService.service_id == service_id, ProfessionalService.location_id == location.id))
            if not linked or not offered:
                continue
            day = start_date
            while day <= end_date:
                schedules = db.scalars(select(ProfessionalSchedule).where(ProfessionalSchedule.professional_id == professional.id, ProfessionalSchedule.location_id == location.id, ProfessionalSchedule.weekday == day.weekday())).all()
                for schedule in schedules:
                    cursor = datetime.combine(day, schedule.start_time, tzinfo=tz)
                    finish = datetime.combine(day, schedule.end_time, tzinfo=tz)
                    while cursor + timedelta(minutes=service.duration_minutes) <= finish:
                        if cursor >= date_from.replace(tzinfo=tz) and cursor <= date_to.replace(tzinfo=tz):
                            try:
                                starts, ends = slot_is_available(db, client_id, location.id, professional.id, service_id, cursor)
                                results.append({"starts_at": starts.replace(tzinfo=timezone.utc), "ends_at": ends.replace(tzinfo=timezone.utc), "location_id": location.id, "professional_id": professional.id, "service_id": service_id})
                            except HTTPException as exc:
                                if exc.status_code not in (409, 422):
                                    raise
                        cursor += timedelta(minutes=slot_minutes)
                day += timedelta(days=1)
    return results


def create_appointment(db: Session, client_id: uuid.UUID, data, *, appointment_id: uuid.UUID | None = None) -> Appointment:
    settings = ensure_enabled(db, client_id)
    # Serialize bookings for the same tenant/professional in PostgreSQL. This
    # prevents two concurrent chatbot requests from selecting the same slot.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"appointments:{client_id}:{data.professional_id}"})
    starts, ends = slot_is_available(db, client_id, data.location_id, data.professional_id, data.service_id, data.starts_at, exclude_id=appointment_id)
    if appointment_id:
        appointment = db.get(Appointment, appointment_id)
        if not appointment or appointment.client_id != client_id:
            raise HTTPException(status_code=404, detail="Appointment not found")
    else:
        appointment = Appointment(client_id=client_id)
        db.add(appointment)
    values = data.model_dump(exclude_unset=True)
    values.pop("starts_at", None)
    values.pop("customer_email", None)
    appointment.location_id = data.location_id
    appointment.professional_id = data.professional_id
    appointment.service_id = data.service_id
    appointment.starts_at = starts
    appointment.ends_at = ends
    appointment.customer_phone = data.customer_phone if hasattr(data, "customer_phone") else appointment.customer_phone
    appointment.customer_name = data.customer_name if hasattr(data, "customer_name") else appointment.customer_name
    appointment.customer_email = str(data.customer_email or "") if hasattr(data, "customer_email") else appointment.customer_email
    appointment.notes = data.notes if hasattr(data, "notes") else appointment.notes
    if hasattr(data, "source"): appointment.source = data.source
    if hasattr(data, "external_id"): appointment.external_id = data.external_id
    if appointment_id: appointment.status = "rescheduled"
    db.flush()
    return appointment


def can_change(db: Session, appointment: Appointment, *, reschedule: bool) -> None:
    settings = get_settings(db, appointment.client_id)
    notice = settings.reschedule_notice_minutes if reschedule else settings.cancellation_notice_minutes
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if appointment.starts_at - now < timedelta(minutes=notice):
        raise HTTPException(status_code=422, detail="This appointment can no longer be changed at this notice")
