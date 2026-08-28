import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import get_current_user
from ...models import Client, User
from ...routers.portal import _portal_client
from .models import Appointment, AppointmentLocation, AppointmentProfessional, AppointmentService, AppointmentSettings, AppointmentTimeOff, ProfessionalLocation, ProfessionalSchedule, ProfessionalService
from .schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate, AvailabilityQuery, AvailabilitySlot, LocationIn, LocationOut, ProfessionalIn, ProfessionalOut, ProfessionalServiceIn, ScheduleIn, ScheduleOut, ServiceIn, ServiceOut, SettingsIn, SettingsOut, TimeOffIn, TimeOffOut
from .service import available_slots, can_change, create_appointment, ensure_enabled, get_settings


admin = APIRouter(prefix="/appointments/clients/{client_id}", tags=["Appointments"])
portal = APIRouter(prefix="/portal/{slug}/appointments", tags=["Portal appointments"])


def client_for(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _professional_out(db: Session, row: AppointmentProfessional) -> ProfessionalOut:
    locations = db.scalars(select(ProfessionalLocation.location_id).where(ProfessionalLocation.professional_id == row.id)).all()
    return ProfessionalOut.model_validate(row).model_copy(update={"location_ids": list(locations)})


@admin.get("/settings", response_model=SettingsOut)
def admin_settings(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id)
    return get_settings(db, client_id)


@admin.put("/settings", response_model=SettingsOut)
def update_settings(client_id: uuid.UUID, payload: SettingsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id)
    row = get_settings(db, client_id)
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    db.commit(); db.refresh(row)
    return row


@admin.get("/locations", response_model=list[LocationOut])
def locations(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id)
    return db.scalars(select(AppointmentLocation).where(AppointmentLocation.client_id == client_id).order_by(AppointmentLocation.name)).all()


@admin.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(client_id: uuid.UUID, payload: LocationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = AppointmentLocation(client_id=client_id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@admin.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(client_id: uuid.UUID, location_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = db.scalar(select(AppointmentLocation).where(AppointmentLocation.id == location_id, AppointmentLocation.client_id == client_id))
    if not row: raise HTTPException(status_code=404, detail="Location not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@admin.get("/professionals", response_model=list[ProfessionalOut])
def professionals(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); return [_professional_out(db, row) for row in db.scalars(select(AppointmentProfessional).where(AppointmentProfessional.client_id == client_id).order_by(AppointmentProfessional.name)).all()]


@admin.post("/professionals", response_model=ProfessionalOut, status_code=status.HTTP_201_CREATED)
def create_professional(client_id: uuid.UUID, payload: ProfessionalIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); location_ids = payload.location_ids; row = AppointmentProfessional(client_id=client_id, name=payload.name, email=str(payload.email or ""), phone=payload.phone, is_active=payload.is_active); db.add(row); db.flush()
    for location_id in location_ids:
        if not db.scalar(select(AppointmentLocation.id).where(AppointmentLocation.id == location_id, AppointmentLocation.client_id == client_id)): raise HTTPException(status_code=422, detail="Invalid location")
        db.add(ProfessionalLocation(professional_id=row.id, location_id=location_id))
    db.commit(); db.refresh(row); return _professional_out(db, row)


@admin.delete("/professionals/{professional_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_professional(client_id: uuid.UUID, professional_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = db.scalar(select(AppointmentProfessional).where(AppointmentProfessional.id == professional_id, AppointmentProfessional.client_id == client_id))
    if not row: raise HTTPException(status_code=404, detail="Professional not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@admin.get("/services", response_model=list[ServiceOut])
def services(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); return db.scalars(select(AppointmentService).where(AppointmentService.client_id == client_id).order_by(AppointmentService.name)).all()


@admin.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(client_id: uuid.UUID, payload: ServiceIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = AppointmentService(client_id=client_id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@admin.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(client_id: uuid.UUID, service_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = db.scalar(select(AppointmentService).where(AppointmentService.id == service_id, AppointmentService.client_id == client_id))
    if not row: raise HTTPException(status_code=404, detail="Service not found")
    db.delete(row); db.commit(); return Response(status_code=204)


def _assert_setup(db: Session, client_id: uuid.UUID, professional_id: uuid.UUID, location_id: uuid.UUID, service_id: uuid.UUID | None = None):
    if not db.scalar(select(AppointmentProfessional.id).where(AppointmentProfessional.id == professional_id, AppointmentProfessional.client_id == client_id)): raise HTTPException(status_code=422, detail="Invalid professional")
    if not db.scalar(select(AppointmentLocation.id).where(AppointmentLocation.id == location_id, AppointmentLocation.client_id == client_id)): raise HTTPException(status_code=422, detail="Invalid location")
    if service_id is not None and not db.scalar(select(AppointmentService.id).where(AppointmentService.id == service_id, AppointmentService.client_id == client_id)): raise HTTPException(status_code=422, detail="Invalid service")


@admin.post("/professional-services", status_code=status.HTTP_201_CREATED)
def link_service(client_id: uuid.UUID, payload: ProfessionalServiceIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); _assert_setup(db, client_id, payload.professional_id, payload.location_id, payload.service_id)
    if not db.scalar(select(ProfessionalLocation.id).where(ProfessionalLocation.professional_id == payload.professional_id, ProfessionalLocation.location_id == payload.location_id)): raise HTTPException(status_code=422, detail="Link the professional to the location first")
    row = ProfessionalService(**payload.model_dump()); db.add(row); db.commit(); return {"id": row.id, **payload.model_dump()}


@admin.post("/professional-locations", status_code=status.HTTP_201_CREATED)
def link_location(client_id: uuid.UUID, payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); professional_id, location_id = uuid.UUID(str(payload["professional_id"])), uuid.UUID(str(payload["location_id"])); _assert_setup(db, client_id, professional_id, location_id); row = ProfessionalLocation(professional_id=professional_id, location_id=location_id); db.add(row); db.commit(); return {"id": row.id, "professional_id": professional_id, "location_id": location_id}


@admin.get("/schedules", response_model=list[ScheduleOut])
def schedules(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); return db.scalars(select(ProfessionalSchedule).join(AppointmentProfessional).where(AppointmentProfessional.client_id == client_id).order_by(ProfessionalSchedule.weekday, ProfessionalSchedule.start_time)).all()


@admin.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(client_id: uuid.UUID, payload: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); _assert_setup(db, client_id, payload.professional_id, payload.location_id); row = ProfessionalSchedule(**payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@admin.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(client_id: uuid.UUID, schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = db.scalar(select(ProfessionalSchedule).join(AppointmentProfessional).where(ProfessionalSchedule.id == schedule_id, AppointmentProfessional.client_id == client_id));
    if not row: raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@admin.get("/time-off", response_model=list[TimeOffOut])
def time_off(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); return db.scalars(select(AppointmentTimeOff).join(AppointmentProfessional).where(AppointmentProfessional.client_id == client_id).order_by(AppointmentTimeOff.starts_at)).all()


@admin.post("/time-off", response_model=TimeOffOut, status_code=status.HTTP_201_CREATED)
def create_time_off(client_id: uuid.UUID, payload: TimeOffIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); if_invalid = payload.ends_at <= payload.starts_at
    if if_invalid: raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    if not db.scalar(select(AppointmentProfessional.id).where(AppointmentProfessional.id == payload.professional_id, AppointmentProfessional.client_id == client_id)): raise HTTPException(status_code=422, detail="Invalid professional")
    row = AppointmentTimeOff(**payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@admin.delete("/time-off/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_off(client_id: uuid.UUID, time_off_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = db.scalar(select(AppointmentTimeOff).join(AppointmentProfessional).where(AppointmentTimeOff.id == time_off_id, AppointmentProfessional.client_id == client_id));
    if not row: raise HTTPException(status_code=404, detail="Time-off not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@admin.post("/availability", response_model=list[AvailabilitySlot])
def admin_availability(client_id: uuid.UUID, payload: AvailabilityQuery, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); return available_slots(db, client_id, **payload.model_dump())


@admin.get("/appointments", response_model=list[AppointmentOut])
def admin_appointments(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); return db.scalars(select(Appointment).where(Appointment.client_id == client_id).order_by(Appointment.starts_at.desc())).all()


@admin.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def admin_create_appointment(client_id: uuid.UUID, payload: AppointmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = create_appointment(db, client_id, payload); db.commit(); db.refresh(row); return row


@admin.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
def admin_update_appointment(client_id: uuid.UUID, appointment_id: uuid.UUID, payload: AppointmentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_for(db, user, client_id); row = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.client_id == client_id))
    if not row: raise HTTPException(status_code=404, detail="Appointment not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("status") == "cancelled":
        can_change(db, row, reschedule=False)
    if "starts_at" in values or "location_id" in values or "professional_id" in values or "service_id" in values:
        data = AppointmentCreate(location_id=values.get("location_id", row.location_id), professional_id=values.get("professional_id", row.professional_id), service_id=values.get("service_id", row.service_id), starts_at=values.get("starts_at", row.starts_at), customer_phone=row.customer_phone, customer_name=values.get("customer_name", row.customer_name), customer_email=values.get("customer_email", row.customer_email) or None, notes=values.get("notes", row.notes), source=row.source, external_id=row.external_id)
        can_change(db, row, reschedule=True); create_appointment(db, client_id, data, appointment_id=row.id); values = {key: value for key, value in values.items() if key not in {"starts_at", "location_id", "professional_id", "service_id"}}
    for key, value in values.items(): setattr(row, key, value)
    db.commit(); db.refresh(row); return row


@portal.get("", response_model=dict)
def portal_info(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    settings = get_settings(db, client.id, create=False)
    return {
        "enabled": bool(settings and settings.enabled),
        "settings": SettingsOut.model_validate(settings) if settings else None,
    }


@portal.get("/locations", response_model=list[LocationOut])
def portal_locations(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); return db.scalars(select(AppointmentLocation).where(AppointmentLocation.client_id == client.id, AppointmentLocation.is_active.is_(True)).order_by(AppointmentLocation.name)).all()


@portal.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def portal_create_location(slug: str, payload: LocationIn, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); row = AppointmentLocation(client_id=client.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@portal.get("/professionals", response_model=list[ProfessionalOut])
def portal_professionals(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); return [_professional_out(db, row) for row in db.scalars(select(AppointmentProfessional).where(AppointmentProfessional.client_id == client.id, AppointmentProfessional.is_active.is_(True)).order_by(AppointmentProfessional.name)).all()]


@portal.post("/professionals", response_model=ProfessionalOut, status_code=status.HTTP_201_CREATED)
def portal_create_professional(slug: str, payload: ProfessionalIn, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); row = AppointmentProfessional(client_id=client.id, name=payload.name, email=str(payload.email or ""), phone=payload.phone, is_active=payload.is_active); db.add(row); db.flush()
    for location_id in payload.location_ids:
        if not db.scalar(select(AppointmentLocation.id).where(AppointmentLocation.id == location_id, AppointmentLocation.client_id == client.id)): raise HTTPException(status_code=422, detail="Invalid location")
        db.add(ProfessionalLocation(professional_id=row.id, location_id=location_id))
    db.commit(); db.refresh(row); return _professional_out(db, row)


@portal.post("/professional-locations", status_code=status.HTTP_201_CREATED)
def portal_link_location(slug: str, payload: dict, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    professional_id = uuid.UUID(str(payload["professional_id"]))
    location_id = uuid.UUID(str(payload["location_id"]))
    _assert_setup(db, client.id, professional_id, location_id)
    existing = db.scalar(select(ProfessionalLocation).where(ProfessionalLocation.professional_id == professional_id, ProfessionalLocation.location_id == location_id))
    if existing:
        return {"id": existing.id, "professional_id": professional_id, "location_id": location_id}
    row = ProfessionalLocation(professional_id=professional_id, location_id=location_id)
    db.add(row); db.commit()
    return {"id": row.id, "professional_id": professional_id, "location_id": location_id}


@portal.post("/professional-services", status_code=status.HTTP_201_CREATED)
def portal_link_service(slug: str, payload: ProfessionalServiceIn, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    _assert_setup(db, client.id, payload.professional_id, payload.location_id, payload.service_id)
    if not db.scalar(select(ProfessionalLocation.id).where(ProfessionalLocation.professional_id == payload.professional_id, ProfessionalLocation.location_id == payload.location_id)):
        raise HTTPException(status_code=422, detail="Link the professional to the location first")
    existing = db.scalar(select(ProfessionalService).where(ProfessionalService.professional_id == payload.professional_id, ProfessionalService.service_id == payload.service_id, ProfessionalService.location_id == payload.location_id))
    if existing:
        return {"id": existing.id, **payload.model_dump()}
    row = ProfessionalService(**payload.model_dump())
    db.add(row); db.commit()
    return {"id": row.id, **payload.model_dump()}


@portal.get("/schedules", response_model=list[ScheduleOut])
def portal_schedules(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    return db.scalars(select(ProfessionalSchedule).join(AppointmentProfessional).where(AppointmentProfessional.client_id == client.id).order_by(ProfessionalSchedule.weekday, ProfessionalSchedule.start_time)).all()


@portal.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def portal_create_schedule(slug: str, payload: ScheduleIn, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    _assert_setup(db, client.id, payload.professional_id, payload.location_id)
    row = ProfessionalSchedule(**payload.model_dump()); db.add(row); db.commit(); db.refresh(row)
    return row


@portal.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def portal_delete_schedule(slug: str, schedule_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    row = db.scalar(select(ProfessionalSchedule).join(AppointmentProfessional).where(ProfessionalSchedule.id == schedule_id, AppointmentProfessional.client_id == client.id))
    if not row: raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@portal.get("/time-off", response_model=list[TimeOffOut])
def portal_time_off(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    return db.scalars(select(AppointmentTimeOff).join(AppointmentProfessional).where(AppointmentProfessional.client_id == client.id).order_by(AppointmentTimeOff.starts_at)).all()


@portal.post("/time-off", response_model=TimeOffOut, status_code=status.HTTP_201_CREATED)
def portal_create_time_off(slug: str, payload: TimeOffIn, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    if payload.ends_at <= payload.starts_at: raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    if not db.scalar(select(AppointmentProfessional.id).where(AppointmentProfessional.id == payload.professional_id, AppointmentProfessional.client_id == client.id)): raise HTTPException(status_code=422, detail="Invalid professional")
    if payload.location_id and not db.scalar(select(AppointmentLocation.id).where(AppointmentLocation.id == payload.location_id, AppointmentLocation.client_id == client.id)): raise HTTPException(status_code=422, detail="Invalid location")
    row = AppointmentTimeOff(**payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@portal.delete("/time-off/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
def portal_delete_time_off(slug: str, time_off_id: uuid.UUID, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    row = db.scalar(select(AppointmentTimeOff).join(AppointmentProfessional).where(AppointmentTimeOff.id == time_off_id, AppointmentProfessional.client_id == client.id))
    if not row: raise HTTPException(status_code=404, detail="Time-off not found")
    db.delete(row); db.commit(); return Response(status_code=204)


@portal.get("/services", response_model=list[ServiceOut])
def portal_services(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); return db.scalars(select(AppointmentService).where(AppointmentService.client_id == client.id, AppointmentService.is_active.is_(True)).order_by(AppointmentService.name)).all()


@portal.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def portal_create_service(slug: str, payload: ServiceIn, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); row = AppointmentService(client_id=client.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@portal.post("/availability", response_model=list[AvailabilitySlot])
def portal_availability(slug: str, payload: AvailabilityQuery, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    return available_slots(db, client.id, **payload.model_dump())


@portal.get("/appointments", response_model=list[AppointmentOut])
def portal_appointments(slug: str, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id); return db.scalars(select(Appointment).where(Appointment.client_id == client.id).order_by(Appointment.starts_at)).all()


@portal.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def portal_create_appointment(slug: str, payload: AppointmentCreate, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    row = create_appointment(db, client.id, payload); db.commit(); db.refresh(row); return row


@portal.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
def portal_update_appointment(slug: str, appointment_id: uuid.UUID, payload: AppointmentUpdate, client: Client = Depends(_portal_client), db: Session = Depends(get_db)):
    ensure_enabled(db, client.id)
    row = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.client_id == client.id))
    if not row: raise HTTPException(status_code=404, detail="Appointment not found")
    if payload.status == "cancelled": can_change(db, row, reschedule=False); row.status = "cancelled"
    elif payload.starts_at: can_change(db, row, reschedule=True); data = AppointmentCreate(location_id=payload.location_id or row.location_id, professional_id=payload.professional_id or row.professional_id, service_id=payload.service_id or row.service_id, starts_at=payload.starts_at, customer_phone=row.customer_phone, customer_name=payload.customer_name or row.customer_name, customer_email=payload.customer_email or row.customer_email or None, notes=payload.notes or row.notes, source=row.source, external_id=row.external_id); create_appointment(db, client.id, data, appointment_id=row.id)
    db.commit(); db.refresh(row); return row
