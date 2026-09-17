"use client";

import { useEffect, useState } from "react";
import { CalendarDays, CheckCircle2, ExternalLink, LoaderCircle, ShieldCheck, Unplug } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useT, type I18nKey } from "@/lib/i18n";
import { Alert, Modal } from "@/components/ui";
import { useToast } from "@/components/toast";
import type { GoogleCalendarIntegration, GoogleCalendarTool } from "@/types";

export function GoogleCalendarIntegration({ agentId }: { agentId: string }) {
  const t = useT();
  const toast = useToast();
  const [integration, setIntegration] = useState<GoogleCalendarIntegration | null>(null);
  const [tools, setTools] = useState<GoogleCalendarTool[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const base = `/agents/${agentId}/integrations/google-calendar`;
  async function load() {
    try { setIntegration(await api<GoogleCalendarIntegration>(base)); }
    catch (error) { toast.error(messageFrom(error)); }
  }
  useEffect(() => { load(); }, [agentId]);

  async function connect() {
    setBusy(true);
    try {
      const result = await api<{ authorization_url: string }>(`${base}/oauth/start`, {
        method: "POST", body: JSON.stringify({ next_path: `/agents/${agentId}?tab=integrations` }),
      });
      window.location.assign(result.authorization_url);
    } catch (error) { toast.error(messageFrom(error)); setBusy(false); }
  }

  async function manage() {
    setBusy(true);
    try {
      const listed = await api<GoogleCalendarTool[]>(`${base}/tools`);
      setTools(listed); setOpen(true);
    } catch (error) { toast.error(messageFrom(error)); }
    finally { setBusy(false); }
  }

  async function save() {
    setBusy(true);
    try {
      const updated = await api<GoogleCalendarIntegration>(`${base}/tools`, {
        method: "PUT", body: JSON.stringify({ enabled_tools: tools.filter((tool) => tool.enabled).map((tool) => tool.name) }),
      });
      setIntegration(updated); setOpen(false); toast.success(t("tools.googleCalendar.save"));
    } catch (error) { toast.error(messageFrom(error)); }
    finally { setBusy(false); }
  }

  async function disconnect() {
    if (!confirm(t("tools.googleCalendar.disconnectConfirm"))) return;
    setBusy(true);
    try { await api(base, { method: "DELETE" }); setOpen(false); await load(); }
    catch (error) { toast.error(messageFrom(error)); }
    finally { setBusy(false); }
  }

  const enabled = integration?.enabled_tools.length ?? 0;
  return <>
    <section className="panel calendar-integration-panel">
      <div className="panel-head"><div><h3>{t("tools.googleCalendar.heading")}</h3><p>{t("tools.googleCalendar.copy")}</p></div></div>
      <div className="calendar-integration-row">
        <span className="calendar-integration-icon"><CalendarDays size={22} /></span>
        <div className="calendar-integration-copy"><strong>{t("tools.googleCalendar.name")}</strong><small>{t("tools.googleCalendar.description")}</small>
          {integration?.connected && <span className="calendar-connected"><CheckCircle2 size={14} /> {t("tools.googleCalendar.connected")} · {t("tools.googleCalendar.enabledCount", { count: enabled })}</span>}
          {integration?.status === "error" && <span className="calendar-error">{t("tools.googleCalendar.connectionError")}</span>}
        </div>
        {integration?.connected ? <button className="button secondary" disabled={busy} onClick={manage}>{busy ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />} {t("tools.googleCalendar.manage")}</button>
          : <button className="button primary" disabled={busy || !integration?.oauth_ready} onClick={connect}>{busy ? <LoaderCircle className="spin" size={16} /> : <ExternalLink size={16} />} {t("tools.googleCalendar.connect")}</button>}
      </div>
      {integration && !integration.oauth_ready && <div className="calendar-config-note">{t("tools.googleCalendar.unavailable")}</div>}
    </section>
    <Modal open={open} wide title={t("tools.googleCalendar.configureTitle")} description={t("tools.googleCalendar.configureCopy")} onClose={() => setOpen(false)}>
      <div className="calendar-tools-modal">
        {integration?.last_error && <Alert>{integration.last_error}</Alert>}
        <div className="calendar-tools-list">
          {tools.map((tool) => <label className="switch-row calendar-tool-row" key={tool.name}>
            <span><strong>{tool.name.replace(/^google_calendar_/, "")}</strong><small>{t(`tools.googleCalendar.methods.${tool.name}` as I18nKey)}</small><em>{tool.read_only ? t("tools.googleCalendar.readOnly") : t("tools.googleCalendar.changesData")}</em></span>
            <input type="checkbox" checked={tool.enabled} onChange={() => setTools((current) => current.map((item) => item.name === tool.name ? { ...item, enabled: !item.enabled } : item))} />
          </label>)}
        </div>
        <div className="modal-actions calendar-modal-actions"><button className="button danger" disabled={busy} onClick={disconnect}><Unplug size={16} /> {t("tools.googleCalendar.disconnect")}</button><span /><button className="button secondary" onClick={() => setOpen(false)}>{t("tools.form.cancel")}</button><button className="button primary" disabled={busy} onClick={save}>{busy && <LoaderCircle className="spin" size={16} />}{busy ? t("tools.googleCalendar.saving") : t("tools.googleCalendar.save")}</button></div>
      </div>
    </Modal>
  </>;
}
