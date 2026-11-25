import { ArrowLeft, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { Notice } from "../components/Feedback";
import { PageHeader } from "../components/Page";
import { useGroupContext } from "../lib/group-context";
import { navigate } from "../lib/router";

export function CreateGroupPage() {
  const { refresh, selectGroup } = useGroupContext();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [initialSync, setInitialSync] = useState<{ status: string; message?: string | null; found_count?: number; added_count?: number; updated_count?: number } | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSubmitting(true); const form = new FormData(event.currentTarget); try { const group = await api.createGroup({ name: String(form.get("name")), discord_server_id: String(form.get("discord_server_id")) || null, combined_statistics: form.get("combined_statistics") === "on", primary_alliance_name: String(form.get("alliance_name")), primary_alliance_tag: String(form.get("alliance_tag")), primary_alliance_state_id: String(form.get("state_id")), assign_legacy_events: false, confirm_legacy_assignment: false }); selectGroup(group.id); await refresh({ groupId: group.id }); setInitialSync(group.initial_sync ?? null); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to create group."); } finally { setSubmitting(false); } };
  if (initialSync) return <div className="page"><PageHeader title="Alliance group created" description="The primary alliance is ready for scoped records." /><Notice tone={initialSync.status === "failed" ? "error" : "success"}>{initialSync.status === "success" ? `Initial roster import: ${initialSync.found_count ?? 0} found, ${initialSync.added_count ?? 0} added, ${initialSync.updated_count ?? 0} updated.` : initialSync.message ?? "Synchronization is not configured. You can start it later from Alliance groups."}</Notice><button className="button button--primary" onClick={() => navigate("/groups")}>Continue to alliance settings</button></div>;
  return <div className="page"><button className="back-link back-link--page" onClick={() => navigate("/groups")}><ArrowLeft size={17} />Alliance groups</button><PageHeader title="Create alliance group" description="Each new group begins with exactly one primary alliance and its own future access boundary." /><section className="editor-panel editor-panel--narrow"><form className="record-form" onSubmit={submit}><label>Group name <span>*</span><input name="name" required /></label><label>Primary alliance name <span>*</span><input name="alliance_name" required /></label><div className="form-columns"><label>Tag <span>*</span><input name="alliance_tag" required /></label><label>State ID <span>*</span><input name="state_id" required /></label></div><label>Discord Server ID <input name="discord_server_id" /></label><label className="check-row"><input name="combined_statistics" type="checkbox" /> <span>Combine future statistics across linked alliances</span></label>{error && <Notice tone="error">{error}</Notice>}<button className="button button--primary" disabled={submitting} type="submit"><Plus size={16} />{submitting ? "Creating…" : "Create group"}</button></form></section></div>;
}
