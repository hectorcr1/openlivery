"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, CalendarDays, Clock3, MapPin, Plus, Trash2, UserRound } from "lucide-react";
import { Alert, EmptyState } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Appointment, AppointmentLocation, AppointmentProfessional, AppointmentService, AppointmentSettings } from "@/types";

type Info = { enabled: boolean; settings: AppointmentSettings | null };

export default function AppointmentsPage() {
  const t = useT();
  const { slug } = useParams<{ slug: string }>();
  const [info, setInfo] = useState<Info | null>(null);
  const [locations, setLocations] = useState<AppointmentLocation[]>([]);
  const [professionals, setProfessionals] = useState<AppointmentProfessional[]>([]);
  const [services, setServices] = useState<AppointmentService[]>([]);
  const [bookings, setBookings] = useState<Appointment[]>([]);
  const [error, setError] = useState("");
  const load = async () => {
    const status = await api<Info>(`/portal/${slug}/appointments`);
    setInfo(status);
    if (!status.enabled) return;
    const [nextLocations, nextProfessionals, nextServices, nextBookings] = await Promise.all([
      api<AppointmentLocation[]>(`/portal/${slug}/appointments/locations`),
      api<AppointmentProfessional[]>(`/portal/${slug}/appointments/professionals`),
      api<AppointmentService[]>(`/portal/${slug}/appointments/services`),
      api<Appointment[]>(`/portal/${slug}/appointments/appointments`),
    ]);
    setLocations(nextLocations); setProfessionals(nextProfessionals); setServices(nextServices); setBookings(nextBookings);
  };
  useEffect(() => { load().catch((err) => setError(messageFrom(err))); }, [slug]);
  if (error) return <main className="portal-loader"><Alert>{error}</Alert></main>;
  if (!info) return <main className="portal-loader">{t("common.loading")}</main>;
  if (!info.enabled) return <main className="portal-loader"><Alert>{t("appointments.disabled")}</Alert><Link href={`/portal/${slug}`} className="button secondary">{t("appointments.back")}</Link></main>;
  return <main className="portal-app portal-module" style={{ "--portal-color": "#075985" } as React.CSSProperties}>
    <aside className="portal-nav"><div className="portal-brand"><span><CalendarDays size={18} /></span><strong>{t("appointments.title")}</strong></div><nav><Link href={`/portal/${slug}`}><ArrowLeft size={18} /> {t("appointments.back")}</Link><a className="active"><CalendarDays size={18} /> {t("appointments.title")}</a></nav></aside>
    <section className="portal-main"><header><div><small>{t("appointments.title")}</small><h1>{t("appointments.subtitle")}</h1></div></header>
      <div className="appointment-grid"><ResourceForm slug={slug} kind="location" onSaved={load} /><ResourceForm slug={slug} kind="professional" locations={locations} onSaved={load} /><ResourceForm slug={slug} kind="service" onSaved={load} /></div>
      <section className="form-section"><div className="section-copy"><h2>{t("appointments.bookings")}</h2><p>{t("appointments.portalHint")}</p></div>{bookings.length ? <div className="table-shell"><table className="data-table"><thead><tr><th>{t("appointments.appointment")}</th><th>{t("appointments.customer")}</th><th>{t("appointments.date")}</th><th>{t("appointments.status")}</th><th /></tr></thead><tbody>{bookings.map((booking) => <tr key={booking.id}><td><strong>{services.find((item) => item.id === booking.service_id)?.name || booking.service_id.slice(0, 8)}</strong><small>{professionals.find((item) => item.id === booking.professional_id)?.name || ""} · {locations.find((item) => item.id === booking.location_id)?.name || ""}</small></td><td>{booking.customer_name || booking.customer_phone}</td><td>{new Date(booking.starts_at).toLocaleString()}</td><td><span className={`mini-badge ${booking.status}`}>{booking.status}</span></td><td>{booking.status !== "cancelled" && <button className="text-button danger-text" onClick={async () => { await api(`/portal/${slug}/appointments/appointments/${booking.id}`, { method: "PATCH", body: JSON.stringify({ status: "cancelled" }) }); await load(); }}><Trash2 size={15} /> {t("appointments.cancel")}</button>}</td></tr>)}</tbody></table></div> : <EmptyState icon={<CalendarDays />} title={t("appointments.empty")} description={t("appointments.portalHint")} />}</section>
    </section>
  </main>;
}

function ResourceForm({ slug, kind, locations = [], onSaved }: { slug: string; kind: "location" | "professional" | "service"; locations?: AppointmentLocation[]; onSaved: () => Promise<void> }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); setBusy(true); setError("");
    try {
      const base = `/portal/${slug}/appointments`;
      const payload = kind === "location" ? { name: data.get("name"), address: data.get("address") } : kind === "professional" ? { name: data.get("name"), email: data.get("email"), phone: data.get("phone"), location_ids: data.getAll("location_ids") } : { name: data.get("name"), duration_minutes: Number(data.get("duration_minutes")), buffer_before_minutes: Number(data.get("buffer_before_minutes") || 0), buffer_after_minutes: Number(data.get("buffer_after_minutes") || 0) };
      await api(`${base}/${kind === "location" ? "locations" : kind === "professional" ? "professionals" : "services"}`, { method: "POST", body: JSON.stringify(payload) }); form.reset(); await onSaved();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  return <form className="form-section" onSubmit={submit}><div className="section-copy"><h2>{kind === "location" ? <><MapPin size={17} /> {t("appointments.locations")}</> : kind === "professional" ? <><UserRound size={17} /> {t("appointments.professionals")}</> : <><Clock3 size={17} /> {t("appointments.services")}</>}</h2><p>{kind === "location" ? t("appointments.addLocation") : kind === "professional" ? t("appointments.addProfessional") : t("appointments.addService")}</p></div><div className="form-fields"><label>{t("appointments.name")}<input name="name" required /></label>{kind === "location" && <label>{t("appointments.address")}<input name="address" /></label>}{kind === "professional" && <><label>{t("appointments.email")}<input name="email" type="email" /></label><label>{t("appointments.phone")}<input name="phone" /></label><label>{t("appointments.locations")}<select name="location_ids" multiple>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label></>}{kind === "service" && <div className="form-grid"><label>{t("appointments.duration")}<input name="duration_minutes" type="number" min={5} defaultValue={60} required /></label><label>{t("appointments.bufferBefore")}<input name="buffer_before_minutes" type="number" min={0} defaultValue={0} /></label><label>{t("appointments.bufferAfter")}<input name="buffer_after_minutes" type="number" min={0} defaultValue={0} /></label></div>}{error && <Alert>{error}</Alert>}<button className="button secondary" disabled={busy}><Plus size={15} /> {t("appointments.save")}</button></div></form>;
}
