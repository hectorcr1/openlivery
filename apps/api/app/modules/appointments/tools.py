import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Appointment, AppointmentService, AppointmentSettings
from .schemas import AppointmentCreate, AvailabilityQuery
from .service import available_slots, can_change, create_appointment, ensure_enabled


def _json(value) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _service(db: Session, client_id: uuid.UUID, service_id: str):
    service = db.scalar(select(AppointmentService).where(AppointmentService.id == uuid.UUID(service_id), AppointmentService.client_id == client_id, AppointmentService.is_active.is_(True)))
    if not service: raise ValueError("Service not found")
    return service


def execute_appointment_tool(db: Session, client_id: uuid.UUID, name: str, args: dict) -> tuple[str, bool]:
    try:
        ensure_enabled(db, client_id)
        if name == "appointments_find_availability":
            rows = available_slots(db, client_id, **AvailabilityQuery.model_validate(args).model_dump())
            return _json(rows[:100]), False
        if name == "appointments_book":
            payload = AppointmentCreate.model_validate({**args, "source": "whatsapp"})
            row = create_appointment(db, client_id, payload); db.commit(); db.refresh(row)
            return _json({"id": row.id, "status": row.status, "starts_at": row.starts_at, "ends_at": row.ends_at}), False
        appointment = db.scalar(select(Appointment).where(Appointment.id == uuid.UUID(str(args.get("appointment_id"))), Appointment.client_id == client_id))
        if not appointment: raise ValueError("Appointment not found")
        if name == "appointments_get": return _json(appointment), False
        if name == "appointments_cancel":
            can_change(db, appointment, reschedule=False); appointment.status = "cancelled"; db.commit(); return _json({"id": appointment.id, "status": appointment.status}), False
        if name == "appointments_reschedule":
            can_change(db, appointment, reschedule=True)
            data = AppointmentCreate(location_id=uuid.UUID(str(args.get("location_id", appointment.location_id))), professional_id=uuid.UUID(str(args.get("professional_id", appointment.professional_id))), service_id=uuid.UUID(str(args.get("service_id", appointment.service_id))), starts_at=datetime.fromisoformat(str(args["starts_at"])), customer_phone=appointment.customer_phone, customer_name=appointment.customer_name, customer_email=appointment.customer_email or None, notes=appointment.notes, source="whatsapp", external_id=appointment.external_id)
            row = create_appointment(db, client_id, data, appointment_id=appointment.id); db.commit(); db.refresh(row); return _json({"id": row.id, "status": row.status, "starts_at": row.starts_at, "ends_at": row.ends_at}), False
        raise ValueError(f"Unknown appointment tool: {name}")
    except Exception as exc:
        db.rollback()
        return str(exc), True
