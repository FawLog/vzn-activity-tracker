import { EventIcon } from "../components/EventIcon";
import { CalendarPlus, CheckCircle2, UserPlus, Shield } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { UpcomingEvents } from "../components/UpcomingEvents";
import { AllianceAnalytics } from "../components/AllianceAnalytics";
import { PageHeader, SectionHeader } from "../components/Page";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventLabel, formatDate, formatTimestamp, shortElapsed, observationInterval } from "../lib/format";
import { navigate } from "../lib/router";
import type { OverviewData } from "../lib/types";

function AllianceEmblem({url,tag}:{url:string|null;tag:string}){
  const [failed,setFailed]=useState(false);
  let allowed=false;
  try {const parsed=new URL(url??"");allowed=parsed.protocol==="https:"&&parsed.hostname==="gof-formal-avatar.akamaized.net"&&!parsed.username&&!parsed.password&&(!parsed.port||parsed.port==="443")}catch{/* missing or invalid URL */}
  return <div className="alliance-emblem">{allowed&&!failed?<img src={url!} alt={tag+" alliance flag"} onError={()=>setFailed(true)} />:<div className="alliance-emblem-fallback" role="img" aria-label={tag+" alliance emblem unavailable"}><Shield size={25} aria-hidden="true"/><span>{tag}</span></div>}</div>;
}
export function OverviewPage() {
  const { selectedGroup, selectedAlliance, alliances } = useGroupContext();
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState("");
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const id=window.setInterval(()=>setNow(Date.now()),60000);return()=>window.clearInterval(id)},[]);

  useEffect(() => {
    let live=true;setData(null);setError("");
    if (selectedGroup) api.overview(selectedGroup.id, selectedAlliance?.id).then(v=>{if(live)setData(v)}).catch((requestError) => {if(live)setError(requestError.message)});
    return ()=>{live=false};
  }, [selectedGroup, selectedAlliance]);

  if (!selectedGroup) return <div className="page"><PageHeader title="Operational overview" description="Set up an alliance group before viewing scoped records." /><EmptyState title="No active group" description="Create the first primary alliance to start the evidence record." action={<button className="button button--primary" onClick={() => navigate("/onboarding")}>Start setup</button>} /></div>;

  const alliance=data?.alliance;
  const tag=alliance?.external_tag??selectedAlliance?.tag??"—";
  const age=shortElapsed(alliance?.source_observed_at,now);
  const interval=observationInterval(alliance?.previous_source_observed_at,alliance?.source_observed_at);
  return (
    <div className="page intelligence-page overview-page">
      <PageHeader
        title="Operational overview"
        description="A verified record of alliance participation, contribution, and reliability."
      />
      <div className="evidence-line"><CheckCircle2 size={18} /><strong>Evidence status:</strong><span>{data?.published_events ? `${data.published_events} published event${data.published_events === 1 ? "" : "s"}` : "No published data yet"}</span></div>

      {alliance ? <section className="data-panel alliance-intelligence"><SectionHeader title="Alliance intelligence" description="WhiteoutStats · latest available observation" />
        <div className="alliance-identity">
          <AllianceEmblem key={alliance.flag_url??tag} url={alliance.flag_url} tag={tag}/>
          <div><small>Alliance · {tag}</small><strong>{alliance.external_name??selectedAlliance?.name??"—"}</strong><span>State {alliance.state_id??"—"}</span></div>
        </div>
        <div className="stats-grid">
          <div className="alliance-power"><small>Total power</small><strong>{alliance.power?.toLocaleString()??"—"}</strong>{alliance.power_change!=null&&interval&&<span className="power-delta" title="Change between the two latest distinct WhiteoutStats observations">{alliance.power_change>0?"+":""}{alliance.power_change.toLocaleString()} <small>since previous sync · {interval}</small></span>}</div>
          <div className="alliance-members"><small>Members</small><strong>{alliance.member_count??"—"}</strong></div>
          <div className="alliance-state-rank"><small>State power rank</small><strong>{alliance.power_rank?"#"+alliance.power_rank:"—"}</strong></div>
          <div className="alliance-leader"><small>Leader</small><strong>{alliance.leader_name??"—"}</strong></div>
          <div className="alliance-observation"><small>Last observation</small><strong title={formatTimestamp(alliance.source_observed_at)}>{age?age+" ago":"—"}</strong><span>{formatTimestamp(alliance.source_observed_at)}</span></div>
        </div></section> : selectedAlliance ? <EmptyState compact title="No alliance statistics yet" description="Run WhiteoutStats Sync once configured; no external values are inferred." /> : null}

      <UpcomingEvents key={selectedGroup.id} groupId={selectedGroup.id} alliances={alliances} selectedAllianceId={selectedAlliance?.id} now={now}/>
      <AllianceAnalytics key={selectedGroup.id+":"+selectedAlliance?.id} groupId={selectedGroup.id} allianceId={selectedAlliance?.id??""} allianceLabel={selectedAlliance?.tag??"Selected alliance"}/>
      {!data?.published_events&&<section className="foundation-banner">
        <div className="foundation-banner__content">
          <h2>The intelligence picture starts with verified records</h2>
          <p>Add alliance players and enter scheduled event data to build a trusted, reviewable history. Missing evidence is never converted to zero.</p>
          <div className="button-row">
            <><button className="button button--primary" onClick={() => navigate("/admin?mode=players")}><UserPlus size={18} />Add player</button><button className="button button--secondary" disabled={!selectedAlliance} onClick={() => navigate("/calendar")}><CalendarPlus size={18} />Open calendar</button></>
          </div>
        </div>
      </section>}

      {error ? <ErrorState message={error} /> : !data ? <LoadingState /> : (
        <div className="analytics-recent">
          <section className="data-panel">
            <SectionHeader title="Recent event records" description="Actual drafts and published records, most recent first." action={<button className="button button--quiet" onClick={() => navigate("/events")}>Event history</button>} />
            {data.recent_events.length === 0 ? (
              <EmptyState compact title="No events yet" description="Enter data from a scheduled event in Calendar. Historical records are available in Event history." action={<button className="button button--secondary" onClick={() => navigate("/calendar")}>Open calendar</button>} />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Event</th><th>Date</th><th>Status</th><th className="number-cell">Participants</th></tr></thead>
                  <tbody>{data.recent_events.map((event) => (
                    <tr key={event.id} className="clickable-row">
                      <td><button className="table-link event-name" onClick={() => navigate(`/events/${event.id}`)}><EventIcon eventType={event.event_type}/><span>{eventLabel(event.event_type)}</span></button></td><td>{formatDate(event.occurred_on)}</td><td><span className={`status status--${event.status}`}>{event.status}</span></td><td className="number-cell">{event.participant_count ?? "—"}</td>
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
