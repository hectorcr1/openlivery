"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ExternalLink, Link2, LoaderCircle, Search, ShieldCheck, Unplug, X } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useToast } from "@/components/toast";
import { ConfirmModal } from "@/components/confirm-modal";
import { Modal } from "@/components/ui";

type Toolkit = {
  slug: string;
  name: string;
  description: string;
  logo: string;
  categories: string[];
  tools_count?: number;
  managed_auth?: boolean;
  installed?: boolean;
  connected?: boolean;
  assigned?: boolean;
  tool_slugs?: string[];
};
type Overview = { configured: boolean; client_id: string; items: Toolkit[] };
type CatalogPage = { items: Toolkit[]; next_cursor: string | null };
type Tool = { slug: string; name: string; description: string; read_only: boolean; destructive: boolean; supported: boolean };

export function ComposioSection({ agentId, onToolsChange }: { agentId: string; onToolsChange: () => void }) {
  const t = useT();
  const toast = useToast();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [catalog, setCatalog] = useState<Toolkit[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [editing, setEditing] = useState<Toolkit | null>(null);
  const [tools, setTools] = useState<Tool[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [toolsBusy, setToolsBusy] = useState(false);
  const [disconnecting, setDisconnecting] = useState<Toolkit | null>(null);

  async function refresh() {
    const data = await api<Overview>(`/composio/agents/${agentId}`);
    setOverview(data);
  }

  useEffect(() => {
    refresh().catch((err) => toast.error(messageFrom(err)));
  }, [agentId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("composio");
    if (!result) return;
    toast[result === "connected" ? "success" : "error"](t(result === "connected" ? "composio.oauthSuccess" : "composio.oauthFailed"));
    params.delete("composio");
    const search = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
  }, [t, toast]);

  async function loadCatalog(next: string | null = null) {
    setCatalogBusy(true);
    try {
      const page = await api<CatalogPage>(`/composio/catalog?limit=40${next ? `&cursor=${encodeURIComponent(next)}` : ""}`);
      setCatalog((current) => next ? [...current, ...page.items] : page.items);
      setCursor(page.next_cursor);
    } catch (err) { toast.error(messageFrom(err)); } finally { setCatalogBusy(false); }
  }

  async function install(item: Toolkit) {
    setBusySlug(item.slug);
    try {
      await api("/composio/install", { method: "POST", body: JSON.stringify({ slug: item.slug }) });
      await refresh();
      setCatalog((current) => current.map((entry) => entry.slug === item.slug ? { ...entry, installed: true } : entry));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusySlug(null); }
  }

  async function connect(item: Toolkit) {
    setBusySlug(item.slug);
    try {
      const result = await api<{ authorization_url: string }>(`/composio/agents/${agentId}/connect/${item.slug}`, { method: "POST" });
      window.location.assign(result.authorization_url);
    } catch (err) { toast.error(messageFrom(err)); setBusySlug(null); }
  }

  async function openTools(item: Toolkit) {
    setEditing(item);
    setToolsBusy(true);
    setTools([]);
    try {
      const available = await api<Tool[]>(`/composio/toolkits/${item.slug}/tools`);
      setTools(available);
      setSelected(new Set(item.assigned ? item.tool_slugs || [] : available.filter((tool) => tool.supported && tool.read_only).slice(0, 20).map((tool) => tool.slug)));
    } catch (err) { toast.error(messageFrom(err)); setEditing(null); } finally { setToolsBusy(false); }
  }

  function toggleTool(slug: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(slug)) next.delete(slug);
      else if (next.size < 20) next.add(slug);
      return next;
    });
  }

  async function saveTools() {
    if (!editing || !selected.size) return;
    setToolsBusy(true);
    try {
      await api(`/composio/agents/${agentId}/assign/${editing.slug}`, {
        method: "PUT",
        body: JSON.stringify({ tool_slugs: [...selected] }),
      });
      await refresh();
      onToolsChange();
      setEditing(null);
    } catch (err) { toast.error(messageFrom(err)); } finally { setToolsBusy(false); }
  }

  async function removeTools(item: Toolkit) {
    setBusySlug(item.slug);
    try {
      await api(`/composio/agents/${agentId}/assign/${item.slug}`, { method: "DELETE" });
      await refresh();
      onToolsChange();
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusySlug(null); }
  }

  async function disconnect(item: Toolkit) {
    await api(`/composio/agents/${agentId}/connect/${item.slug}`, { method: "DELETE" });
    await refresh();
    onToolsChange();
  }

  const categories = useMemo(() => [...new Set(catalog.flatMap((item) => item.categories))].sort(), [catalog]);
  const visibleCatalog = catalog.filter((item) => {
    const matchesQuery = `${item.name} ${item.description} ${item.slug}`.toLowerCase().includes(query.toLowerCase());
    return matchesQuery && (!category || item.categories.includes(category));
  });

  return (
    <section className="panel composio-panel">
      <div className="panel-head">
        <div><h3>{t("composio.heading")}</h3><p>{t("composio.copy")}</p></div>
        {overview?.configured && <button className="button secondary" type="button" onClick={() => { setCatalogOpen((value) => !value); if (!catalog.length) loadCatalog(); }}>
          {catalogOpen ? <X size={15} /> : <Search size={15} />}{t("composio.browse")}
        </button>}
      </div>
      {!overview && <div className="composio-notice"><LoaderCircle size={18} className="spin" />{t("composio.loading")}</div>}
      {overview && !overview.configured && <div className="composio-notice"><ShieldCheck size={19} /><div><strong>{t("composio.setupTitle")}</strong><span>{t("composio.setupCopy")}</span></div></div>}

      {!!overview?.items.length && <div className="composio-installed">
        {overview.items.map((item) => <div className="composio-installed-row" key={item.slug}>
          <span className="composio-monogram" aria-hidden="true">{item.name.slice(0, 1).toUpperCase()}</span>
          <div className="composio-installed-main"><strong>{item.name}</strong><small>{item.connected ? t("composio.connected") : t("composio.notConnected")}</small></div>
          {item.assigned && <span className="pill green">{t("composio.assigned", { count: item.tool_slugs?.length || 0 })}</span>}
          <div className="composio-installed-actions">
            {!item.connected ? <button type="button" className="button primary" disabled={busySlug === item.slug} onClick={() => connect(item)}><Link2 size={14} />{t("composio.connect")}</button>
              : <><button type="button" className="button secondary" disabled={busySlug === item.slug} onClick={() => openTools(item)}>{t("composio.manage")}</button>
                {item.assigned && <button type="button" className="icon-button" disabled={busySlug === item.slug} onClick={() => removeTools(item)} title={t("composio.remove")} aria-label={t("composio.remove")}><X size={16} /></button>}
                <button type="button" className="icon-button danger-icon" onClick={() => setDisconnecting(item)} title={t("composio.disconnect")} aria-label={t("composio.disconnect")}><Unplug size={16} /></button></>}
          </div>
        </div>)}
      </div>}
      {overview?.configured && !overview.items.length && !catalogOpen && <div className="composio-notice"><Link2 size={19} /><span>{t("composio.installedEmpty")}</span></div>}

      {catalogOpen && overview?.configured && <div className="composio-catalog">
        <div className="composio-catalog-controls">
          <label className="composio-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("composio.search")} /></label>
          <label className="composio-category"><span className="sr-only">{t("composio.categoryAll")}</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">{t("composio.categoryAll")}</option>{categories.map((name) => <option key={name}>{name}</option>)}</select><ChevronDown size={15} /></label>
        </div>
        <div className="composio-directory">
          {visibleCatalog.map((item) => <div className="composio-directory-row" key={item.slug}>
            <span className="composio-monogram" aria-hidden="true">{item.name.slice(0, 1).toUpperCase()}</span>
            <div><strong>{item.name}</strong><small>{item.description}</small><span>{item.categories[0]} · {t("composio.toolCount", { count: item.tools_count || 0 })} · {t(item.managed_auth ? "composio.managedAuth" : "composio.customAuth")}</span></div>
            <button type="button" className={item.installed ? "button secondary" : "button primary"} disabled={item.installed || !item.managed_auth || busySlug === item.slug} onClick={() => install(item)}>{item.installed ? <Check size={14} /> : <ExternalLink size={14} />}{t(item.installed ? "composio.installed" : "composio.install")}</button>
          </div>)}
          {!visibleCatalog.length && !catalogBusy && <div className="composio-directory-empty">{t("composio.catalogEmpty")}</div>}
        </div>
        {cursor && <button type="button" className="button secondary composio-more" disabled={catalogBusy} onClick={() => loadCatalog(cursor)}>{catalogBusy && <LoaderCircle className="spin" size={14} />}{t("composio.loadMore")}</button>}
      </div>}

      <Modal open={!!editing} title={editing?.name || ""} description={t("composio.selectHint")} onClose={() => setEditing(null)} wide>
        <div className="composio-tool-modal">
          <div className="composio-tool-count">{t("composio.selectedCount", { count: selected.size })}</div>
          {toolsBusy && !tools.length && <div className="composio-notice"><LoaderCircle className="spin" size={17} />{t("composio.loading")}</div>}
          <div className="composio-tool-list">{tools.map((tool) => <label className={`composio-tool-row ${tool.supported ? "" : "disabled"}`} key={tool.slug}>
            <input type="checkbox" checked={selected.has(tool.slug)} disabled={!tool.supported || (!selected.has(tool.slug) && selected.size >= 20)} onChange={() => toggleTool(tool.slug)} />
            <span><strong>{tool.name || tool.slug}</strong><small>{tool.description}</small><em>{tool.slug}</em></span>
            <span className={`pill ${tool.read_only ? "green" : "red"}`}>{t(tool.supported ? tool.read_only ? "composio.readOnly" : "composio.changesData" : "composio.unavailable")}</span>
          </label>)}</div>
          {!toolsBusy && !tools.length && <div className="composio-directory-empty">{t("composio.noTools")}</div>}
          <div className="composio-modal-actions"><button type="button" className="button secondary" onClick={() => setEditing(null)}>{t("composio.cancel")}</button><button type="button" className="button primary" disabled={toolsBusy || !selected.size} onClick={saveTools}>{toolsBusy && <LoaderCircle className="spin" size={14} />}{t(toolsBusy ? "composio.saving" : "composio.save")}</button></div>
        </div>
      </Modal>
      {disconnecting && <ConfirmModal title={t("composio.disconnectTitle")} message={t("composio.disconnectCopy")} confirmLabel={t("composio.disconnect")} cancelLabel={t("composio.cancel")} confirmIcon={<Unplug size={15} />} onConfirm={() => disconnect(disconnecting)} onClose={() => setDisconnecting(null)} />}
    </section>
  );
}
