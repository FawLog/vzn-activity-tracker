import { ArrowLeft, CalendarDays, FileCheck2 } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventLabel, formatDate } from "../lib/format";
import { navigate } from "../lib/router";
import { ManualEventEditor, supportsManualEditor } from "../components/ManualEventEditor";
import type { EventRecord } from "../lib/types";

export function EventDetailPage({ id }: { id: string }) {
  const { selectedGroup } = useGroupContext();
  const [record, setRecord] = useState<EventRecord | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (selectedGroup) api.event(selectedGroup.id, id).then(setRecord).catch((requestError) => setError(requestError.message)); }, [id, selectedGroup]);
  if (!selectedGroup) return <div className="page"><LoadingState label="Selecting group" /></div>;
  if (error) return <div className="page"><ErrorState message={error} /></div>;
  if (!record) return <div className="page"><LoadingState label="Loading event record" /></div>;
  return <div className="page"><button className="back-link back-link--page" onClick={() => navigate("/events")}><ArrowLeft size={18} />Events</button><header className="event-header"><div><span className="event-header__type"><CalendarDays size={17} />{eventLabel(record.event_type)}</span><h1>{formatDate(record.occurred_on)}</h1><p>{record.alliance_name ?? "Alliance"} · <span className={`status status--${record.status}`}>{record.status}</span></p></div><span className="event-header__id mono">ID {record.id.slice(0, 12)}</span></header>{supportsManualEditor(record.event_type) && <ManualEventEditor key={selectedGroup.id + ":" + record.id} groupId={selectedGroup.id} record={record} onPublished={() => setRecord({...record,status:"published"})} />}{(!supportsManualEditor(record.event_type) || !!record.participants?.length) && <section className="data-panel data-panel--page"><div className="section-header"><div><h2>Legacy results</h2><p>Participation and raw event-specific values will appear here after review.</p></div><FileCheck2 size={20} /></div>{record.participants?.length ? <div className="table-wrap"><table><thead><tr><th>FID</th><th>Player</th><th>Presence</th><th>Roster role</th><th>Raw points</th></tr></thead><tbody>{record.participants.map((participant) => <tr key={participant.fid}><td className="mono">{participant.fid}</td><td>{participant.nickname}</td><td>{participant.presence_status.replaceAll("_", " ")}</td><td>{participant.roster_role ?? "Unknown"}</td><td>{participant.raw_points ?? "—"}</td></tr>)}</tbody></table></div> : <EmptyState compact title="No reviewed results" description="No participant result records have been added to this event." />}</section>}</div>;
}
