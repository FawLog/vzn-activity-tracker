import { FileClock, LockKeyhole, Plus, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { EmptyState, ErrorState, LoadingState, Notice } from "../components/Feedback";
import { PageHeader, SectionHeader } from "../components/Page";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventTypeOptions, formatTimestamp } from "../lib/format";
import type { AuditRecord } from "../lib/types";

type Mode = "players" | "events";

export function AdminPage() {
  const { selectedGroup, selectedAlliance } = useGroupContext();
  const queryMode = new URLSearchParams(window.location.search).get("mode");
  const [mode, setMode] = useState<Mode>(queryMode === "events" ? "events" : "players");
  const [audit, setAudit] = useState<AuditRecord[] | null>(null);
  const [auditError, setAuditError] = useState("");
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const refreshAudit = useCallback(() => {
    api.audit().then((result) => setAudit(result.items)).catch((requestError) => setAuditError(requestError.message));
  }, []);
  useEffect(refreshAudit, [refreshAudit]);

  const createPlayer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSubmitting(true); setMessage(null);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    if (!selectedGroup) return;
    try { await api.createPlayer(selectedGroup.id, { fid: String(form.get("fid") ?? ""), nickname: String(form.get("nickname") ?? "") }); formElement.reset(); setMessage({ tone: "success", text: "Player record created in the selected group." }); refreshAudit(); }
    catch (requestError) { setMessage({ tone: "error", text: requestError instanceof Error ? requestError.message : "Unable to create player." }); }
    finally { setSubmitting(false); }
  };

  const createEvent = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSubmitting(true); setMessage(null);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    if (!selectedGroup || !selectedAlliance) return;
    try { await api.createEvent(selectedGroup.id, selectedAlliance.id, { event_type: String(form.get("event_type") ?? ""), occurred_on: String(form.get("occurred_on") ?? ""), status: String(form.get("status") ?? "draft") }); formElement.reset(); setMessage({ tone: "success", text: "Event record created for the selected alliance." }); refreshAudit(); }
    catch (requestError) { setMessage({ tone: "error", text: requestError instanceof Error ? requestError.message : "Unable to create event." }); }
    finally { setSubmitting(false); }
  };

  if (!selectedGroup || !selectedAlliance) return <div className="page"><PageHeader title="Administration" description="Select a group and alliance before creating records." /></div>;
  return <div className="page"><PageHeader title="Administration" description={`Create records in ${selectedGroup.name} / ${selectedAlliance.name}.`} /><div className="privacy-note"><LockKeyhole size={18} />Records remain restricted until access controls are expanded.</div><div className="admin-tabs" role="tablist"><button className={mode === "players" ? "active" : ""} onClick={() => setMode("players")} role="tab" aria-selected={mode === "players"}>Players</button><button className={mode === "events" ? "active" : ""} onClick={() => setMode("events")} role="tab" aria-selected={mode === "events"}>Events</button></div><div className="admin-layout"><section className="editor-panel">{mode === "players" ? <><SectionHeader title="Create player" description="FID is global; this creates an unconfirmed profile only in the selected group." /><form className="record-form" onSubmit={createPlayer}><label>FID <span>*</span><input name="fid" maxLength={32} required autoComplete="off" /><small>Primary game identifier</small></label><label>Nickname <span>*</span><input name="nickname" maxLength={80} required autoComplete="off" /><small>Current display name</small></label>{message && <Notice tone={message.tone}>{message.text}</Notice>}<button className="button button--primary" type="submit" disabled={submitting}><UserPlus size={17} />{submitting ? "Saving…" : "Add player"}</button></form></> : <><SectionHeader title="Create event" description={`Draft is the safe default. This event will belong to ${selectedAlliance.name}.`} /><form className="record-form" onSubmit={createEvent}><label>Event type <span>*</span><select name="event_type" required defaultValue=""><option value="" disabled>Select event type</option>{eventTypeOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Event date <span>*</span><input name="occurred_on" type="date" required /></label><fieldset><legend>Status <span>*</span></legend><label className="radio"><input type="radio" name="status" value="draft" defaultChecked />Draft</label><label className="radio"><input type="radio" name="status" value="published" />Published</label></fieldset>{message && <Notice tone={message.tone}>{message.text}</Notice>}<button className="button button--primary" type="submit" disabled={submitting}><Plus size={17} />{submitting ? "Saving…" : "Create event"}</button></form></>}</section><section className="audit-panel"><SectionHeader title="Activity / Audit" description="Attributed changes made in Administration." action={<FileClock size={20} />} />{auditError ? <ErrorState message={auditError} /> : !audit ? <LoadingState label="Loading audit history" /> : audit.length === 0 ? <EmptyState compact title="No changes recorded" description="Create a player or event to see attributed activity here." /> : <div className="table-wrap"><table><thead><tr><th>Action</th><th>Record</th><th>Author</th><th>Time</th></tr></thead><tbody>{audit.map((item) => <tr key={item.id}><td>{item.action}</td><td><strong>{item.entity_type}</strong><small className="table-subline mono">{item.entity_id.slice(0, 14)}</small></td><td>{item.actor}</td><td>{formatTimestamp(item.created_at)}</td></tr>)}</tbody></table></div>}</section></div></div>;
}
