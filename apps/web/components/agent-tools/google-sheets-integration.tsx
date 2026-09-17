"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, FileSpreadsheet, LoaderCircle, ShieldCheck, Unplug } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useT, type I18nKey } from "@/lib/i18n";
import { Alert, Modal } from "@/components/ui";
import { useToast } from "@/components/toast";
import type { GoogleSheetsIntegration, GoogleSheetsTool } from "@/types";

export function GoogleSheetsIntegration({ agentId }: { agentId: string }) {
  const t = useT();
  const toast = useToast();
  const [integration, setIntegration] = useState<GoogleSheetsIntegration | null>(null);
  const [tools, setTools] = useState<GoogleSheetsTool[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const base = `/agents/${agentId}/integrations/google-sheets`;

  async function load() {
    try { setIntegration(await api<GoogleSheetsIntegration>(base)); }
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
    try { setTools(await api<GoogleSheetsTool[]>(`${base}/tools`)); setOpen(true); }
    catch (error) { toast.error(messageFrom(error)); }
    finally { setBusy(false); }
  }

  async function save() {
    setBusy(true);
    try {
      const updated = await api<GoogleSheetsIntegration>(`${base}/tools`, {
        method: "PUT", body: JSON.stringify({ enabled_tools: tools.filter((tool) => tool.enabled).map((tool) => tool.name) }),
      });
      setIntegration(updated); setOpen(false); toast.success(t("tools.googleSheets.save"));
    } catch (error) { toast.error(messageFrom(error)); }
    finally { setBusy(false); }
  }

  async function disconnect() {
    if (!confirm(t("tools.googleSheets.disconnectConfirm"))) return;
    setBusy(true);
    try { await api(base, { method: "DELETE" }); setOpen(false); await load(); }
    catch (error) { toast.error(messageFrom(error)); }
    finally { setBusy(false); }
  }

  const enabled = integration?.enabled_tools.length ?? 0;
  return <>
    <section className="panel calendar-integration-panel">
      <div className="calendar-integration-row">
        <span className="calendar-integration-icon sheets-integration-icon"><FileSpreadsheet size={22} /></span>
        <div className="calendar-integration-copy"><strong>{t("tools.googleSheets.name")}</strong><small>{t("tools.googleSheets.description")}</small>
          {integration?.connected && <span className="calendar-connected"><CheckCircle2 size={14} /> {t("tools.googleSheets.connected")} · {t("tools.googleSheets.enabledCount", { count: enabled })}</span>}
          {integration?.status === "error" && <span className="calendar-error">{t("tools.googleSheets.connectionError")}</span>}
        </div>
        {integration?.connected ? <button className="button secondary" disabled={busy} onClick={manage}>{busy ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />} {t("tools.googleSheets.manage")}</button>
          : <button className="button primary" disabled={busy || !integration?.oauth_ready} onClick={connect}>{busy ? <LoaderCircle className="spin" size={16} /> : <ExternalLink size={16} />} {t("tools.googleSheets.connect")}</button>}
      </div>
      {integration && !integration.oauth_ready && <div className="calendar-config-note">{t("tools.googleSheets.unavailable")}</div>}
    </section>
    <Modal open={open} wide title={t("tools.googleSheets.configureTitle")} description={t("tools.googleSheets.configureCopy")} onClose={() => setOpen(false)}>
      <div className="calendar-tools-modal">
        {integration?.last_error && <Alert>{integration.last_error}</Alert>}
        <div className="calendar-tools-list">
          {tools.map((tool) => <label className="switch-row calendar-tool-row" key={tool.name}>
            <span><strong>{tool.name.replace(/^google_sheets_/, "")}</strong><small>{t(`tools.googleSheets.methods.${tool.name}` as I18nKey)}</small><em>{tool.read_only ? t("tools.googleSheets.readOnly") : t("tools.googleSheets.changesData")}</em></span>
            <input type="checkbox" checked={tool.enabled} onChange={() => setTools((current) => current.map((item) => item.name === tool.name ? { ...item, enabled: !item.enabled } : item))} />
          </label>)}
        </div>
        <div className="modal-actions calendar-modal-actions"><button className="button danger" disabled={busy} onClick={disconnect}><Unplug size={16} /> {t("tools.googleSheets.disconnect")}</button><span /><button className="button secondary" onClick={() => setOpen(false)}>{t("tools.form.cancel")}</button><button className="button primary" disabled={busy} onClick={save}>{busy && <LoaderCircle className="spin" size={16} />}{busy ? t("tools.googleSheets.saving") : t("tools.googleSheets.save")}</button></div>
      </div>
    </Modal>
  </>;
}
