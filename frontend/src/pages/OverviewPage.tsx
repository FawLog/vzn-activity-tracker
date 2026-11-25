import { CalendarPlus, CheckCircle2, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { AllianceAnalytics } from "../components/AllianceAnalytics";
import { PageHeader, SectionHeader } from "../components/Page";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventLabel, formatDate, formatTimestamp } from "../lib/format";
import { navigate } from "../lib/router";
import type { OverviewData } from "../lib/types";

export function OverviewPage() {
  const { selectedGroup, selectedAlliance } = useGroupContext();
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live=true;setData(null);setError("");
    if (selectedGroup) api.overview(selectedGroup.id, selectedAlliance?.id).then(v=>{if(live)setData(v)}).catch((requestError) => {if(live)setError(requestError.message)});
    return ()=>{live=false};
  }, [selectedGroup, selectedAlliance]);

  if (!selectedGroup) return <div className="page"><PageHeader title="Operational overview" description="Set up an alliance group before viewing scoped records." /><EmptyState title="No active group" description="Create the first primary alliance to start the evidence record." action={<button className="button button--primary" onClick={() => navigate("/onboarding")}>Start setup</button>} /></div>;

  return (
    <div className="page">
      <PageHeader
        title="Operational overview"
        description="A verified record of alliance participation, contribution, and reliability."
      />
      <div className="evidence-line"><CheckCircle2 size={18} /><strong>Evidence status:</strong><span>{data?.published_events ? `${data.published_events} published event${data.published_events === 1 ? "" : "s"}` : "No published data yet"}</span></div>

      {data?.alliance ? <section className="data-panel alliance-intelligence"><SectionHeader title="Alliance intelligence" description="External WhiteoutStats observations are separate from local administrative settings." />
        <div className="stats-grid">
          {data.alliance.flag_url ? <img className="alliance-flag" src={data.alliance.flag_url} alt="" /> : null}
          <div><small>Alliance</small><strong>{data.alliance.external_name ?? selectedAlliance?.name} {data.alliance.external_tag ? `· ${data.alliance.external_tag}` : ""}</strong></div>
          <div><small>State</small><strong>{data.alliance.state_id ?? "—"}</strong></div>
          <div><small>Total power</small><strong>{data.alliance.power?.toLocaleString() ?? "—"}{data.alliance.power_change !== null ? <em> {data.alliance.power_change >= 0 ? "+" : ""}{data.alliance.power_change.toLocaleString()}</em> : null}</strong></div>
          <div><small>Members</small><strong>{data.alliance.member_count ?? "—"}</strong></div>
          <div><small>State power rank</small><strong>{data.alliance.power_rank ? `#${data.alliance.power_rank}` : "—"}</strong></div>
          <div><small>Leader</small><strong>{data.alliance.leader_name ?? "—"}</strong></div>
          <div><small>Observed</small><strong>{formatTimestamp(data.alliance.source_observed_at)}</strong></div>
        </div></section> : selectedAlliance ? <EmptyState compact title="No alliance statistics yet" description="Run WhiteoutStats Sync once configured; no external values are inferred." /> : null}

      <AllianceAnalytics key={selectedGroup.id+":"+selectedAlliance?.id} groupId={selectedGroup.id} allianceId={selectedAlliance?.id??""} allianceLabel={selectedAlliance?.tag??"Selected alliance"}/>
      {!data?.published_events&&<section className="foundation-banner">
        <div className="foundation-banner__content">
          <h2>The intelligence picture starts with verified records</h2>
          <p>Add alliance players and create event records to build a trusted, reviewable history. Missing evidence is never converted to zero.</p>
          <div className="button-row">
            <><button className="button button--primary" onClick={() => navigate("/admin?mode=players")}><UserPlus size={18} />Add player</button><button className="button button--secondary" disabled={!selectedAlliance} onClick={() => navigate("/admin?mode=events")}><CalendarPlus size={18} />Create event</button></>
          </div>
        </div>
      </section>}

      {error ? <ErrorState message={error} /> : !data ? <LoadingState /> : (
        <div className="analytics-recent">
          <section className="data-panel">
            <SectionHeader title="Recent events" description="Verified alliance event records, most recent first." action={<button className="button button--quiet" onClick={() => navigate("/admin?mode=events")}><CalendarPlus size={16} />Create event</button>} />
            {data.recent_events.length === 0 ? (
              <EmptyState compact title="No events yet" description="Create an event and it will appear here with its date, status, and participant count." action={<button className="button button--secondary" onClick={() => navigate("/admin?mode=events")}>Create event</button>} />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Event</th><th>Date</th><th>Status</th><th className="number-cell">Participants</th></tr></thead>
                  <tbody>{data.recent_events.map((event) => (
                    <tr key={event.id} className="clickable-row">
                      <td><button className="table-link" onClick={() => navigate(`/events/${event.id}`)}>{eventLabel(event.event_type)}</button></td><td>{formatDate(event.occurred_on)}</td><td><span className={`status status--${event.status}`}>{event.status}</span></td><td className="number-cell">{event.participant_count ?? 0}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>

        </div>
      )}
    </div>
  );
}
