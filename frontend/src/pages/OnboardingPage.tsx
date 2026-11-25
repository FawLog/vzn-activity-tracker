import { CheckCircle2, Database, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { ErrorState, LoadingState, Notice } from "../components/Feedback";
import { AllianceConnection } from "../components/AllianceConnection";
import { PageHeader } from "../components/Page";
import { useGroupContext } from "../lib/group-context";
import { navigate } from "../lib/router";

export function OnboardingPage() {
  const { refresh } = useGroupContext();
  const [status, setStatus] = useState<{ required: boolean; unassigned_legacy_events: number } | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [initialSync, setInitialSync] = useState<{ status: string; message?: string | null; found_count?: number; added_count?: number; updated_count?: number } | null>(null);
  const [allianceTag, setAllianceTag] = useState("");
  const [allianceStateId, setAllianceStateId] = useState("");
  const [previewToken, setPreviewToken] = useState("");
  useEffect(() => { api.onboarding().then(setStatus).catch((requestError) => setError(requestError.message)); }, []);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSubmitting(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const group = await api.completeOnboarding({
        name: String(form.get("name") ?? ""), discord_server_id: String(form.get("discord_server_id") ?? "") || null,
        combined_statistics: form.get("combined_statistics") === "on", primary_alliance_name: String(form.get("alliance_name") ?? ""),
        primary_alliance_tag: String(form.get("alliance_tag") ?? ""), primary_alliance_state_id: String(form.get("state_id") ?? ""), whiteoutstats_preview_token: previewToken || undefined,
        assign_legacy_events: status?.unassigned_legacy_events ? form.get("assign_legacy_events") === "on" : false,
        confirm_legacy_assignment: status?.unassigned_legacy_events ? form.get("confirm_legacy_assignment") === "on" : false,
      });
      await refresh({ groupId: group.id }); setInitialSync(group.initial_sync ?? null);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to complete onboarding."); }
    finally { setSubmitting(false); }
  };
  if (error && !status) return <div className="page"><ErrorState message={error} /></div>;
  if (!status) return <div className="page"><LoadingState label="Checking workspace setup" /></div>;
  if (initialSync) return <div className="page"><PageHeader title="Workspace configured" description="The primary alliance was created and the first roster import was requested." /><Notice tone={initialSync.status === "failed" ? "error" : "success"}>{initialSync.status === "success" ? `Initial roster import: ${initialSync.found_count ?? 0} found, ${initialSync.added_count ?? 0} added, ${initialSync.updated_count ?? 0} updated.` : initialSync.message ?? "Synchronization is not configured. You can start it later from Alliance groups."}</Notice><button className="button button--primary" onClick={() => navigate("/groups")}>Continue to alliance settings</button></div>;
  if (!status.required) return <div className="page"><PageHeader title="Workspace configured" description="Alliance groups are ready for use." /><Notice tone="success">Initial group setup is already complete.</Notice></div>;
  return <div className="page"><PageHeader title="Set up the first alliance group" description="Create a primary alliance before records are assigned to the new group-scoped workspace." />
    <div className="setup-layout"><section className="editor-panel"><form className="record-form" onSubmit={submit}><h2>Group and primary alliance</h2><p>Create exactly one primary alliance. Additional alliances can be added afterward.</p><label>Group name <span>*</span><input name="name" maxLength={120} required /></label><label>Primary alliance name <span>*</span><input name="alliance_name" maxLength={120} required /></label><div className="form-columns"><label>Tag <span>*</span><input name="alliance_tag" maxLength={32} required value={allianceTag} onChange={(event) => { setAllianceTag(event.target.value); setPreviewToken(""); }} /></label><label>State ID <span>*</span><input name="state_id" maxLength={32} required value={allianceStateId} onChange={(event) => { setAllianceStateId(event.target.value); setPreviewToken(""); }} /></label></div><AllianceConnection tag={allianceTag} stateId={allianceStateId} confirmed={Boolean(previewToken)} onConfirmed={setPreviewToken} /><label>Discord Server ID <input name="discord_server_id" maxLength={32} /></label><label className="check-row"><input name="combined_statistics" type="checkbox" /> <span>Combine future statistics across linked alliances</span></label>{status.unassigned_legacy_events > 0 && <div className="legacy-confirm"><Database size={19} /><div><strong>{status.unassigned_legacy_events} legacy event(s) need an owner</strong><p>No event is assigned automatically. Confirm the selected primary alliance is the correct historical owner.</p><label className="check-row"><input name="assign_legacy_events" type="checkbox" required /> <span>Assign all listed legacy events to this primary alliance</span></label><label className="check-row"><input name="confirm_legacy_assignment" type="checkbox" required /> <span>I confirm this historical assignment</span></label></div></div>}{error && <Notice tone="error">{error}</Notice>}<button className="button button--primary" disabled={submitting} type="submit"><CheckCircle2 size={17} />{submitting ? "Saving…" : "Confirm group setup"}</button></form></section><aside className="setup-notes"><ShieldCheck size={22} /><strong>Evidence-safe onboarding</strong><p>Existing player profiles are retained as unconfirmed group profiles. No roster observation or transfer history is invented.</p></aside></div></div>;
}
