import { CalendarPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventLabel, formatDate } from "../lib/format";
import { navigate } from "../lib/router";
import type { EventRecord } from "../lib/types";

export function EventsPage() {
  const { selectedGroup, selectedAlliance } = useGroupContext();
  const [events, setEvents] = useState<EventRecord[] | null>(null);
  const [sortValue, setSortValue] = useState("occurred_on:desc");
  const [error, setError] = useState("");
  useEffect(() => { if (!selectedGroup || !selectedAlliance) return; const [sort, direction] = sortValue.split(":"); setEvents(null); api.events(selectedGroup.id, selectedAlliance.id, sort, direction).then((result) => setEvents(result.items)).catch((requestError) => setError(requestError.message)); }, [selectedGroup, selectedAlliance, sortValue]);
  if (!selectedGroup || !selectedAlliance) return <div className="page"><EmptyState title="No active alliance" description="Select an alliance before viewing events." /></div>;
  return <div className="page"><PageHeader title="Events" description={`Event records for ${selectedAlliance.name}; each event remains tied to this alliance.`} action={<button className="button button--primary" onClick={() => navigate("/admin?mode=events")}><CalendarPlus size={17} />Create event</button>} /><div className="toolbar toolbar--end"><label className="select-control"><span>Sort</span><select value={sortValue} onChange={(event) => setSortValue(event.target.value)}><option value="occurred_on:desc">Newest event date</option><option value="occurred_on:asc">Oldest event date</option><option value="event_type:asc">Event type</option><option value="status:asc">Status</option></select></label></div>{error ? <ErrorState message={error} /> : !events ? <LoadingState label="Loading events" /> : events.length === 0 ? <EmptyState title="No events yet" description="Create the first draft event from Administration. Results can be added in a later milestone." action={<button className="button button--primary" onClick={() => navigate("/admin?mode=events")}>Create event</button>} /> : <section className="data-panel data-panel--page"><div className="table-wrap"><table><thead><tr><th>Event</th><th>Date</th><th>Status</th><th className="number-cell">Participants</th><th /></tr></thead><tbody>{events.map((record) => <tr key={record.id} className="clickable-row"><td><button className="table-link" onClick={() => navigate(`/events/${record.id}`)}>{eventLabel(record.event_type)}</button></td><td>{formatDate(record.occurred_on)}</td><td><span className={`status status--${record.status}`}>{record.status}</span></td><td className="number-cell">{record.participant_count ?? 0}</td><td className="row-arrow">→</td></tr>)}</tbody></table></div></section>}</div>;
}
