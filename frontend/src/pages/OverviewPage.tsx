import { CalendarPlus, CheckCircle2, Layers3, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PageHeader, SectionHeader } from "../components/Page";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { eventLabel, formatDate } from "../lib/format";
import { navigate } from "../lib/router";
import type { OverviewData } from "../lib/types";

export function OverviewPage() {
  const { authenticated } = useAuth();
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authenticated) return;
    api.overview().then(setData).catch((requestError) => setError(requestError.message));
  }, [authenticated]);

  return (
    <div className="page">
      <PageHeader
        title="Operational overview"
        description="A verified record of alliance participation, contribution, and reliability."
      />
      <div className="evidence-line"><CheckCircle2 size={18} /><strong>Evidence status:</strong><span>{data?.published_events ? `${data.published_events} published event${data.published_events === 1 ? "" : "s"}` : "No published data yet"}</span></div>

      <section className="foundation-banner">
        <div className="foundation-banner__content">
          <h2>The intelligence picture starts with verified records</h2>
          <p>Add alliance players and create event records to build a trusted, reviewable history. Missing evidence is never converted to zero.</p>
          <div className="button-row">
            {authenticated ? (
              <>
                <button className="button button--primary" onClick={() => navigate("/admin?mode=players")}><UserPlus size={18} />Add player</button>
                <button className="button button--secondary" onClick={() => navigate("/admin?mode=events")}><CalendarPlus size={18} />Create event</button>
              </>
            ) : (
              <button className="button button--primary" onClick={() => navigate("/login")}>Officer sign-in</button>
            )}
          </div>
        </div>
      </section>

      {!authenticated ? (
        <section className="privacy-rail">
          <ShieldCheck size={24} />
          <div><strong>Private by default</strong><p>Roster records and event details remain unavailable without officer authentication in this foundation release.</p></div>
        </section>
      ) : error ? <ErrorState message={error} /> : !data ? <LoadingState /> : (
        <div className="overview-grid">
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
          <section className="signal-panel">
            <SectionHeader title="Activity signals" description="Independent indicators derived from verified records." />
            {[
              [Layers3, "Contribution", "Raw points stay specific to each event type."],
              [Users, "Attendance", "Confirmed presence, absence, excused, and unknown stay distinct."],
              [ShieldCheck, "Reliability", "Registration commitments are evaluated separately."],
            ].map(([Icon, title, copy]) => {
              const SignalIcon = Icon as typeof Layers3;
              return <div className="signal-row" key={String(title)}><SignalIcon size={22} /><span><strong>{String(title)}</strong><small>{String(copy)}</small></span><em>Unavailable</em></div>;
            })}
          </section>
        </div>
      )}
    </div>
  );
}
