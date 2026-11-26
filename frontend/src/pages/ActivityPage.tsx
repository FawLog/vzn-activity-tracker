import {useEffect,useState} from "react";
import {PageHeader} from "../components/Page";
import {EmptyState,ErrorState,LoadingState} from "../components/Feedback";
import {CountCell,PeriodSelect} from "../components/ActivityShared";
import {api} from "../lib/api";
import {compareCounts,formatTotal,period,type AnalyticsReport,type ActivityPlayer} from "../lib/analytics";
import {useGroupContext} from "../lib/group-context";
import {navigate} from "../lib/router";
type Sort="name"|"bear"|"championship"|"foundry"|"canyon"|"points"|"noShows";
const noShows=(p:ActivityPlayer)=>p.metrics.foundry.no_shows!+p.metrics.canyon.no_shows!;
function compare(a:ActivityPlayer,b:ActivityPlayer,sort:Sort){
 if(sort==="bear")return compareCounts(a.metrics.bear_trap.attendance,b.metrics.bear_trap.attendance);
 if(sort==="championship")return compareCounts(a.metrics.alliance_championship.registration,b.metrics.alliance_championship.registration);
 if(sort==="foundry"||sort==="canyon")return compareCounts(a.metrics[sort].reliability,b.metrics[sort].reliability);
 if(sort==="noShows")return noShows(b)-noShows(a);
 if(sort==="points"){const x=a.metrics.alliance_mobilization.points?.total,y=b.metrics.alliance_mobilization.points?.total;return x==null?(y==null?0:1):y==null?-1:BigInt(x)>BigInt(y)?-1:BigInt(x)<BigInt(y)?1:0}
 return (a.nickname??a.fid).localeCompare(b.nickname??b.fid);
}
export function ActivityPage(){
 const {selectedGroup,selectedAlliance,alliances}=useGroupContext();
 const [days,setDays]=useState(30),[all,setAll]=useState(false),[query,setQuery]=useState(""),[sort,setSort]=useState<Sort>("name");
 const [data,setData]=useState<AnalyticsReport|null>(null),[error,setError]=useState("");
 const gid=selectedGroup?.id,aid=all?"":selectedAlliance?.id;
 useEffect(()=>{let live=true;setData(null);setError("");if(gid&&aid!==undefined){const p=period(days);api.analytics(gid,aid,p.start,p.end).then(v=>{if(live)setData(v)}).catch(e=>{if(live)setError(e.message)})}return()=>{live=false}},[gid,aid,days]);
 const players=(data?.players??[]).filter(p=>((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.trim().toLowerCase())).sort((a,b)=>compare(a,b,sort)||(a.nickname??a.fid).localeCompare(b.nickname??b.fid));
 return <div className="page intelligence-page"><PageHeader title="Player activity" description="Published evidence only. Registration, attendance, reliability and points remain separate."/>
 <div className="activity-toolbar"><PeriodSelect days={days} onChange={setDays}/><label>Scope<select value={all?"all":"selected"} onChange={e=>setAll(e.target.value==="all")}><option value="selected">{selectedAlliance?.tag??"Selected alliance"}</option><option value="all">All alliances</option></select></label><label>Find player<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Nickname or ID"/></label><label>Sort by<select value={sort} onChange={e=>setSort(e.target.value as Sort)}><option value="name">Name</option><option value="bear">Bear attendance (lowest known)</option><option value="championship">Championship (lowest known)</option><option value="foundry">Foundry reliability (lowest known)</option><option value="canyon">Canyon reliability (lowest known)</option><option value="noShows">Most confirmed no-shows</option><option value="points">Mobilization points (highest)</option></select></label></div>
 {!gid?<EmptyState title="No group selected" description="Select a group to see activity."/>:error?<ErrorState message={error}/>:!data?<LoadingState label="Loading activity"/>:<>
 <p className="activity-explainer">{data.published_events} published events · {data.coverage.events_with_sessions} with session evidence · {data.coverage.events_without_sessions} without session evidence. Rates describe known outcomes only; missing records do not count as absences. Bear is counted once per cycle, including academy traps. Historical affiliation unknown: {data.events.filter(e=>e.event_type==="bear_trap").reduce((n,e)=>n+e.unknown_home_players,0)} player-cycle records{all?"":" (excluded from alliance-specific Bear results)"}.</p>
 {!data.published_events?<EmptyState title="No published events in this period" description="Publish reviewed results to start building activity statistics."/>:!players.length?<EmptyState title="No matching player records" description="Change the filter or date period."/>:<section className="data-panel data-panel--page"><div className="table-wrap"><table><thead><tr><th>Player / ID</th><th>Current alliance</th><th>Bear cycles</th><th>Championship</th><th>Mobilization points</th><th>Foundry reliability</th><th>Canyon reliability</th><th>No-shows</th></tr></thead><tbody>{players.map(p=><tr key={p.fid}><td><button className="table-link" onClick={()=>navigate("/players/"+encodeURIComponent(p.fid))}>{p.nickname??p.fid}</button><small className="table-subline mono">{p.fid}</small></td><td>{alliances.find(a=>a.id===p.primary_alliance_id)?.tag??"Unknown"}</td><td><CountCell counts={p.metrics.bear_trap.attendance} positiveLabel="present"/></td><td><CountCell counts={p.metrics.alliance_championship.registration} positiveLabel="registered"/></td><td><span className="activity-cell">{formatTotal(p.metrics.alliance_mobilization.points?.total)}<small>{p.metrics.alliance_mobilization.points?.samples??0} recorded results</small></span></td><td><CountCell counts={p.metrics.foundry.reliability} positiveLabel="attended"/></td><td><CountCell counts={p.metrics.canyon.reliability} positiveLabel="attended"/></td><td className={noShows(p)>0?"activity-negative":""}>{p.metrics.foundry.reliability?.known||p.metrics.canyon.reliability?.known?noShows(p):"—"}</td></tr>)}</tbody></table></div></section>}</>}
 </div>
}
