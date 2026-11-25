import { Archive, Building2, Pencil, Plus, RefreshCw, Save, Settings2, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { EmptyState, LoadingState, Notice } from "../components/Feedback";
import { PageHeader, SectionHeader } from "../components/Page";
import { useGroupContext } from "../lib/group-context";
import { navigate } from "../lib/router";
import type { Alliance, SyncStatus } from "../lib/types";

export function GroupsPage() {
  const { groups, alliances, selectedGroup, selectedAlliance, selectGroup, selectAlliance, refresh, loading } = useGroupContext();
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [editingAllianceId, setEditingAllianceId] = useState<string | null>(null);
  const [syncStatuses, setSyncStatuses] = useState<Record<string, SyncStatus>>({});
  const [syncing, setSyncing] = useState<string | null>(null);
  const editingAlliance = alliances.find((alliance) => alliance.id === editingAllianceId) ?? null;

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!selectedGroup) return;
    void Promise.all(alliances.map(async (alliance) => [alliance.id, await api.allianceSync(selectedGroup.id, alliance.id)] as const))
      .then((items) => setSyncStatuses(Object.fromEntries(items))).catch(() => undefined);
  }, [alliances, selectedGroup]);

  if (loading && !selectedGroup) return <div className="page"><LoadingState label="Loading alliance groups" /></div>;
  if (!selectedGroup) return <div className="page"><PageHeader title="Alliance groups" description="Create the first group before managing linked alliances." /><EmptyState title="No group configured" description="The workspace needs one primary alliance before records can be scoped." action={<button className="button button--primary" onClick={() => navigate("/onboarding")}>Start setup</button>} /></div>;

  const updateGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.updateGroup(selectedGroup.id, {
        name: String(form.get("name")),
        discord_server_id: String(form.get("discord_server_id")) || null,
        combined_statistics: form.get("combined_statistics") === "on",
      });
      setMessage({ tone: "success", text: "Group settings saved." });
      await refresh();
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to save group." });
    }
  };

  const addAlliance = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const alliance = await api.createAlliance(selectedGroup.id, {
        name: String(form.get("name")), tag: String(form.get("tag")), state_id: String(form.get("state_id")),
      });
      setAdding(false);
      selectAlliance(alliance.id);
      const result = alliance as Alliance & { initial_sync?: { status: string; found_count?: number; added_count?: number; updated_count?: number; message?: string } };
      setMessage({ tone: "success", text: result.initial_sync?.status === "success" ? `Initial roster import: ${result.initial_sync.found_count} found, ${result.initial_sync.added_count} added, ${result.initial_sync.updated_count} updated.` : result.initial_sync?.message ?? "Additional alliance added." });
      await refresh({ allianceId: alliance.id });
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to add alliance." });
    }
  };

  const updateAlliance = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingAlliance) return;
    const form = new FormData(event.currentTarget);
    try {
      await api.updateAlliance(selectedGroup.id, editingAlliance.id, {
        name: String(form.get("name")), tag: String(form.get("tag")), state_id: String(form.get("state_id")),
      });
      setEditingAllianceId(null);
      setMessage({ tone: "success", text: "Alliance settings saved." });
      await refresh({ allianceId: editingAlliance.id });
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to save alliance." });
    }
  };

  const archiveAlliance = async (alliance: Alliance) => {
    if (!window.confirm(`Archive ${alliance.name}? Historical records will remain.`)) return;
    try {
      await api.updateAlliance(selectedGroup.id, alliance.id, { status: "archived", confirm_archive: true });
      if (editingAllianceId === alliance.id) setEditingAllianceId(null);
      setMessage({ tone: "success", text: "Alliance archived; historical records are preserved." });
      await refresh();
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to archive alliance." });
    }
  };

  const runSync = async (alliance: Alliance) => {
    setSyncing(alliance.id);
    try {
      const result = await api.syncAllianceNow(selectedGroup.id, alliance.id);
      setMessage({ tone: result.status === "success" ? "success" : "error", text: result.status === "success" ? `Sync complete: ${result.found_count} found, ${result.added_count} added, ${result.updated_count} updated.` : result.message ?? "Synchronization did not complete." });
      setSyncStatuses((current) => ({ ...current, [alliance.id]: { ...(current[alliance.id] ?? {} as SyncStatus), last_sync_status: result.status, last_found_count: result.found_count, last_added_count: result.added_count, last_updated_count: result.updated_count } }));
      await refresh();
    } catch (error) { setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to synchronize." }); }
    finally { setSyncing(null); }
  };

  const toggleSync = async (alliance: Alliance, enabled: boolean) => {
    try {
      const result = await api.updateAllianceSync(selectedGroup.id, alliance.id, enabled);
      setSyncStatuses((current) => ({ ...current, [alliance.id]: result }));
      await refresh();
    } catch (error) { setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to update synchronization." }); }
  };

  return <div className="page"><PageHeader title="Alliance groups" description="Manage independent alliance workspaces. Additional alliances inherit group access rules." /><div className="group-layout"><section className="data-panel group-list"><SectionHeader title="Groups" description="Choose the active workspace." />{groups.map((group) => <button className={`group-row${group.id === selectedGroup.id ? " group-row--selected" : ""}`} key={group.id} onClick={() => { setEditingAllianceId(null); selectGroup(group.id); }}><span><strong>{group.name}</strong><small>{group.alliance_count} alliance{group.alliance_count === 1 ? "" : "s"} · {group.status}</small></span><em>{group.combined_statistics ? "Combined" : "Separate"}</em></button>)}<button className="button button--quiet group-add" onClick={() => navigate("/groups/new")}><Plus size={15} />New group</button></section><section className="group-main">{message && <Notice tone={message.tone}>{message.text}</Notice>}<section className="editor-panel"><SectionHeader title="Group settings" description="Discord access is configured once for the whole group." action={<Settings2 size={19} />} /><form className="record-form" onSubmit={updateGroup}><label>Group name <input name="name" defaultValue={selectedGroup.name} required /></label><label>Discord Server ID <input name="discord_server_id" defaultValue={selectedGroup.discord_server_id ?? ""} /></label><label className="check-row"><input name="combined_statistics" type="checkbox" defaultChecked={Boolean(selectedGroup.combined_statistics)} /> <span>Combine future statistics across linked alliances</span></label><button className="button button--primary" type="submit"><Save size={16} />Save settings</button></form></section><section className="data-panel alliances-panel"><SectionHeader title="Alliances" description="One primary alliance anchors this group; historical records are never deleted." action={<button className="button button--quiet" onClick={() => setAdding((current) => !current)}><Plus size={15} />Add alliance</button>} />{adding && <form className="alliance-inline-form" onSubmit={addAlliance}><input name="name" placeholder="Alliance name" required /><input name="tag" placeholder="Tag" required /><input name="state_id" placeholder="State ID" required /><button className="button button--primary" type="submit">Add</button></form>}{editingAlliance && <form className="alliance-inline-form alliance-inline-form--edit" key={editingAlliance.id} onSubmit={updateAlliance}><label>Alliance name <input aria-label="Alliance name" name="name" defaultValue={editingAlliance.name} required maxLength={120} /></label><label>Tag <input aria-label="Alliance tag" name="tag" defaultValue={editingAlliance.tag} required maxLength={32} /></label><label>State ID <input aria-label="Alliance state ID" name="state_id" defaultValue={editingAlliance.state_id} required maxLength={32} /></label><div className="alliance-inline-form__actions"><button className="button button--primary" type="submit"><Save size={15} />Save alliance</button><button className="button button--quiet" type="button" onClick={() => setEditingAllianceId(null)}><X size={15} />Cancel</button></div></form>}<div className="table-wrap"><table><thead><tr><th>Alliance</th><th>State</th><th>Type</th><th>Status</th><th /></tr></thead><tbody>{alliances.map((alliance) => <tr key={alliance.id} className={alliance.id === selectedAlliance?.id ? "selected-table-row" : ""}><td><button className="table-link" onClick={() => selectAlliance(alliance.id)}><strong>{alliance.name}</strong><small className="table-subline">{alliance.tag}</small></button></td><td className="mono">{alliance.state_id}</td><td>{alliance.alliance_type}</td><td><span className={`status status--${alliance.status === "active" ? "published" : "draft"}`}>{alliance.status}</span></td><td className="alliance-row-actions"><button className="icon-button" aria-label={`Edit ${alliance.name}`} onClick={() => { setAdding(false); setEditingAllianceId(alliance.id); }}><Pencil size={16} /></button>{alliance.alliance_type === "additional" && alliance.status === "active" ? <button className="icon-button" aria-label={`Archive ${alliance.name}`} onClick={() => archiveAlliance(alliance)}><Archive size={16} /></button> : <Building2 size={17} />}</td></tr>)}</tbody></table></div>{alliances.map((alliance) => { const sync = syncStatuses[alliance.id]; return <section className="sync-panel" key={`sync-${alliance.id}`}><strong>WhiteoutStats Sync · {alliance.name}</strong><small>State {alliance.state_id} · tag {alliance.tag} · every 12 hours</small>{sync ? <><span>{sync.api_configured ? (sync.sync_enabled ? "Automatic sync enabled" : "Automatic sync disabled") : "Synchronization is not configured"}</span><span>{sync.last_sync_status ? `Last attempt: ${sync.last_sync_status}` : "No completed import yet"}{sync.last_sync_error ? ` · ${sync.last_sync_error}` : ""}</span><span>{sync.last_sync_status === "success" ? `${sync.last_found_count} found · ${sync.last_added_count} added · ${sync.last_updated_count} updated` : ""}</span><label className="check-row"><input type="checkbox" checked={Boolean(sync.sync_enabled)} disabled={!sync.api_configured || alliance.status !== "active"} onChange={(event) => void toggleSync(alliance, event.target.checked)} /> <span>Enable automatic sync</span></label><button className="button button--secondary" disabled={!sync.api_configured || !sync.sync_enabled || syncing === alliance.id || alliance.status !== "active"} onClick={() => void runSync(alliance)}><RefreshCw size={15} />{syncing === alliance.id ? "Syncing…" : "Sync now"}</button></> : <span>Loading sync status…</span>}</section>; })}</section></section></div></div>;
}
