import {useEffect,useState} from "react";
import {api} from "../lib/api";
import {useGroupContext} from "../lib/group-context";
import {eventName,eventNames,formatTotal,period,type AnalyticsReport,type EventKind} from "../lib/analytics";
import {eventCounts,trend,heatCell,heatLabels,heatMarks,heatmapEvents,overallDistribution,foundryPerformance,type DashboardKind} from "../lib/dashboard";
import {PeriodSelect} from "./ActivityShared";
import {EmptyState,ErrorState,LoadingState} from "./Feedback";
import {navigate} from "../lib/router";
import {overallRows,sortOverall,type OverallRow} from "../lib/overall";
import {PlayerAvatar} from "./PlayerAvatar";
import {PlayerQuickView} from "./PlayerQuickView";

function TrendChart({data,kind}:{data:AnalyticsReport;kind:EventKind}){
 const points=trend(data,kind), known=points.filter(p=>p.value!==null);
 if(!known.length)return <p className="activity-explainer">No known results for this dimension in the selected period.</p>;
 const percentage=kind!=="alliance_mobilization",max=percentage?100:Math.max(1,...known.map(p=>p.value??0)),w=620,h=200,l=62,r=20,t=20,b=34;
 const x=(i:number)=>l+(points.length===1?(w-l-r)/2:i*(w-l-r)/(points.length-1));
 const y=(v:number)=>h-b-v/max*(h-t-b);
 return <div className="analytics-trend"><svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={percentage?"Known outcome percentage by event":"Average recorded points by event"}>
 {[0,.25,.5,.75,1].map(v=><g key={v}><line className="grid-line" x1={l} x2={w-r} y1={y(v*max)} y2={y(v*max)}/><text x={l-7} y={y(v*max)+4} textAnchor="end">{percentage?Math.round(v*100)+"%":Math.round(v*max).toLocaleString(undefined,{notation:"compact"})}</text></g>)}
 {points.map((p,i)=>{const prev=points[i-1];return <g key={p.id}>{i>0&&prev.value!==null&&p.value!==null&&<line className="data-line" x1={x(i-1)} y1={y(prev.value)} x2={x(i)} y2={y(p.value)}/>}
 {p.value!==null&&<circle className="data-point" cx={x(i)} cy={y(p.value)} r={4}><title>{p.date}: {p.value.toLocaleString()}{percentage?"%":""} · {p.known} known samples</title></circle>}
 {(i===0||i===points.length-1||i%Math.max(1,Math.ceil(points.length/5))===0)&&<text x={x(i)} y={h-12} textAnchor="middle">{p.date.slice(5)}</text>}</g>})}</svg>
 <p className="activity-explainer">{percentage?"Known outcome rates; gaps indicate unavailable values.":"Average of recorded point samples, not full-alliance totals."} {known.length} of {points.length} events have chartable evidence.</p>
 <details className="analytics-note"><summary>Chart data</summary><div className="table-wrap"><table><thead><tr><th>Date</th><th>{percentage?"Known rate":"Average recorded points"}</th><th>Known samples</th></tr></thead><tbody>{points.map(p=><tr key={p.id}><td><button className="table-link" onClick={()=>navigate("/events/"+encodeURIComponent(p.id))}>{p.date}</button></td><td>{p.value===null?"—":p.value.toLocaleString()+(percentage?"%":"")}</td><td>{p.known}</td></tr>)}</tbody></table></div></details></div>
}
function FoundrySummary({data}:{data:AnalyticsReport}){
 const s=foundryPerformance(data);
 return <><div className="section-header"><div><h2>Foundry performance</h2><p>Verified legion outcomes · independent of Activity Score</p></div></div><div className="analytics-summary"><div><small>Win rate</small><strong>{s.rate===null?"—":s.rate+"%"}</strong><span>{s.wins} victories · {s.losses} defeats · {s.unknown} unknown</span></div>{(["legion_1","legion_2"] as const).map(key=>{const x=s.byLegion[key];return <div key={key}><small>{key.replaceAll("_"," ")}</small><strong>{x.rate===null?"—":x.rate+"%"}</strong><span>{x.wins}W / {x.losses}L · {x.unknown} unknown</span></div>})}<div><small>Attendance</small><strong>{s.attendance.rate===null?"—":s.attendance.rate+"%"}</strong><span>{s.attendance.positive}/{s.attendance.known} known · {s.attendance.unknown} unknown</span></div><div><small>Registration</small><strong>{s.registration.rate===null?"—":s.registration.rate+"%"}</strong><span>{s.registration.positive}/{s.registration.known} known · {s.registration.unknown} unknown</span></div><div><small>Missed without registration</small><strong>{s.missedUnregistered}</strong><span>{s.missedRegistered} missed after registration</span></div></div>{s.battles.length>0&&<div className="table-wrap"><table><thead><tr><th>Date / Legion</th><th>Opponent</th><th>Team score</th><th>Outcome</th></tr></thead><tbody>{s.battles.slice(-10).reverse().map(b=><tr key={b.eventId+":"+b.session_key}><td><button className="table-link" onClick={()=>navigate("/events/"+encodeURIComponent(b.eventId))}>{b.date} · {b.session_key.replaceAll("_"," ")}</button></td><td>{b.opponent_tag?"["+b.opponent_tag+"] ":""}{b.opponent_name??"—"}{b.opponent_state&&<small className="table-subline">#{b.opponent_state}</small>}</td><td>{b.own_score?.toLocaleString()??"—"} : {b.opponent_score?.toLocaleString()??"—"}</td><td className={b.outcome==="victory"?"activity-positive":b.outcome==="defeat"?"activity-negative":""}>{b.outcome??"Unknown"}</td></tr>)}</tbody></table></div>}</>;
}
function OverallSummary({rows}:{rows:OverallRow[]}){
 const d=overallDistribution(rows);
 const max=Math.max(1,...d.bins.map(b=>b.count));
 return <div className="overall-overview-summary">
  <div className="overall-overview-totals"><div><small>Active members</small><strong>{rows.length}</strong></div><div><small>Covered scores</small><strong>{d.covered}</strong></div><div><small>Provisional scores</small><strong>{d.provisional}</strong></div><div><small>No score</small><strong>{d.unscored}</strong></div></div>
  {d.covered+d.provisional>0?<div className="overall-distribution" role="group" aria-label="Activity score distribution">{d.bins.map(b=><div key={b.label} className="overall-distribution-row"><span>{b.label}</span><div className="overall-distribution-track" aria-hidden="true"><div style={{width:100*b.count/max+"%"}}/></div><strong>{b.count}</strong></div>)}</div>:<p className="activity-explainer">No calculated scores for the selected active roster yet.</p>}
  <p className="activity-explainer">Distribution of the same advisory Activity Score used in Rankings, for the selected period and alliance scope. Provisional scores have incomplete evidence; no score is not zero. This is a period summary, not a historical trend.</p>
 </div>;
}
export function AllianceAnalytics({groupId,allianceId,allianceLabel}:{groupId:string;allianceId:string;allianceLabel:string}){
 const [days,setDays]=useState(30),[scope,setScope]=useState<string|null>(null),[kind,setKind]=useState<DashboardKind>("overall"),[query,setQuery]=useState(""),[limit,setLimit]=useState(50);
 const {alliances}=useGroupContext();
 const activeScope=scope===null?allianceId:scope;
 const all=activeScope==="";
 useEffect(()=>{setScope(null)},[groupId,allianceId]);
 const [selected,setSelected]=useState<string|null>(null);
 const [data,setData]=useState<AnalyticsReport|null>(null),[error,setError]=useState("");
 useEffect(()=>{let live=true;setData(null);setError("");setSelected(null);const p=period(days);api.analytics(groupId,activeScope,p.start,p.end).then(v=>{if(live)setData(v)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[groupId,activeScope,days]);
 const events=data?heatmapEvents(data,kind):[];
 const overall=data?overallRows(data):[];
 const scores=new Map(overall.map(r=>[r.player.fid,r]));
 const active=data?.players.find(p=>p.fid===selected);
 const matches=(data?.players??[]).filter(p=>((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.trim().toLowerCase()));
 const order=new Map(sortOverall(overall,"score",false).map((r,i)=>[r.player.fid,i]));
 const players=kind==="overall"?[...matches].sort((a,b)=>(order.get(a.fid)??Infinity)-(order.get(b.fid)??Infinity)||(a.nickname??a.fid).localeCompare(b.nickname??b.fid)):matches;
 return <section className="data-panel analytics-panel"><div className="section-header"><div><h2>Alliance activity</h2><p>Published event evidence · independent dimensions</p></div><button className="button button--quiet" onClick={()=>navigate("/activity")}>Player activity →</button></div>
 <div className="activity-toolbar"><PeriodSelect days={days} onChange={setDays}/><label>Scope<select value={activeScope} onChange={e=>setScope(e.target.value)}>{alliances.filter(a=>a.group_id===groupId&&a.status==="active").map(a=><option key={a.id} value={a.id}>{a.id===allianceId?allianceLabel:a.name}</option>)}<option value="">All alliances</option></select></label></div>
 {error?<ErrorState message={error}/>:!data?<LoadingState label="Loading alliance analytics"/>:!data.published_events?<EmptyState compact title="No published events in this period" description="Publish reviewed event results to populate charts and activity statistics."/>:<>
 <div className="analytics-summary"><div><small>Published events</small><strong>{data.published_events}</strong><span>{data.coverage.events_with_sessions} with session evidence</span></div>{(["alliance_championship","bear_trap","foundry","canyon"] as const).map(k=>{const c=eventCounts(data,k);return <div key={k}><small>{eventNames[k]} {k==="alliance_championship"?"registration":k==="bear_trap"?"attendance":"reliability"}</small><strong>{c?.rate==null?"—":c.rate+"%"}</strong><span>{c?.positive??0}/{c?.known??0} known · {c?.unknown??0} unknown</span></div>})}<div><small>Mobilization recorded points</small><strong>{formatTotal(data.events.some(e=>e.metrics.points?.total!=null)?data.events.reduce((n,e)=>n+BigInt(e.event_type==="alliance_mobilization"?e.metrics.points?.total??"0":"0"),0n).toString():null)}</strong><span>Recorded samples only</span></div></div>
 <details className="analytics-note"><summary>Data coverage</summary><p className="activity-explainer">Rates exclude unknown and excused outcomes; recorded rows are not a historical roster. {data.coverage.events_without_sessions} events without session evidence. {!all&&"Bear player-cycle records with unknown historical affiliation excluded: "+data.events.filter(e=>e.event_type==="bear_trap").reduce((n,e)=>n+e.unknown_home_players,0)+"."}</p></details>
 <div className="activity-toolbar"><label>Event type<select aria-label="Event type" value={kind} onChange={e=>{setKind(e.target.value as DashboardKind);setLimit(50)}}><option value="overall">Overall</option>{Object.entries(eventNames).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label></div>
 {kind==="foundry"&&<FoundrySummary data={data}/>}
 {kind==="overall"?<><div className="section-header"><div><h2>Overall activity</h2><p>Activity score distribution · current active members</p></div></div><OverallSummary rows={overall}/></>:<><div className="section-header"><div><h2>{eventNames[kind]} trend</h2><p>{kind==="alliance_mobilization"?"Average recorded points":kind==="alliance_championship"?"Registration among known outcomes":kind==="bear_trap"?"Attendance among known cycles":"Reliability among registered players with known attendance"}</p></div></div><TrendChart data={data} kind={kind}/></>}
 <div className="section-header"><div><h2>Activity heatmap</h2><p>{kind==="overall"?"Latest 40 published events across all supported types":"Latest 40 events of selected type"} · one column per event</p></div></div>
 <p className="activity-explainer">{kind==="overall"?"Lowest Activity Score first; unscored and historical players last. Each event keeps its own evidence meaning: registration, attendance or recorded contribution.":kind==="alliance_championship"?"Registration, not battle participation.":kind==="alliance_mobilization"?"Recorded results, not attendance.":kind==="bear_trap"?"One outcome per group Bear cycle.":"Attendance across recorded legions; mixed outcomes are retained."}</p>
 <div className="activity-toolbar"><label>Find player<input value={query} onChange={e=>{setQuery(e.target.value);setLimit(50)}} placeholder="Nickname or ID"/></label></div>
 <div className="analytics-legend">{Object.entries(heatLabels).map(([key,label])=><span key={key}><i className={"heat-"+key}/>{label}</span>)}</div>
 {!events.length?<EmptyState compact title="No events of this type" description="Select another event type or period."/>:!players.length?<EmptyState compact title="No matching players" description="Change the search filter."/>:<><div className="table-wrap analytics-heatmap"><table><thead><tr><th>Player</th>{kind==="overall"&&<th>Activity score</th>}{events.map(e=><th key={e.id}><button className="table-link heatmap-event-link" title={eventName(e.event_type)+" · "+e.occurred_on} onClick={()=>navigate("/events/"+encodeURIComponent(e.id))}>{kind==="overall"&&<span>{eventName(e.event_type)}</span>}<small>{e.occurred_on.slice(5)}</small></button></th>)}</tr></thead><tbody>{players.slice(0,limit).map(p=><tr key={p.fid}><td><button className="table-link roster-player" aria-haspopup="dialog" onClick={()=>setSelected(p.fid)}><PlayerAvatar url={p.avatar_url}/><span>{p.nickname??p.fid}</span></button></td>{kind==="overall"&&<td>{scores.get(p.fid)?.score?.toFixed(1)??"—"}<small className="table-subline">{scores.get(p.fid)?.score==null?"No score":scores.get(p.fid)?.provisional?"Provisional":"Covered"}</small></td>}{events.map(e=>{const cell=heatCell(e,p.fid);return <td key={e.id}><span className={"heat-cell heat-"+cell} title={heatLabels[cell]} aria-label={heatLabels[cell]}>{heatMarks[cell]}</span></td>})}</tr>)}</tbody></table></div>{players.length>limit&&<button className="button button--quiet analytics-more" onClick={()=>setLimit(n=>n+50)}>Load more ({limit} of {players.length})</button>}</>}
 </>}{data&&active&&<PlayerQuickView key={data.group_id+":"+active.fid} groupId={data.group_id} activityPlayer={active} row={scores.get(active.fid)} start={data.start} end={data.end} onClose={()=>setSelected(null)}/>}</section>
}
