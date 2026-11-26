import {useEffect,useState} from "react";
import {api} from "../lib/api";
import {eventNames,formatTotal,period,type AnalyticsReport,type EventKind} from "../lib/analytics";
import {eventCounts,trend,heatCell,heatLabels,heatMarks} from "../lib/dashboard";
import {PeriodSelect} from "./ActivityShared";
import {EmptyState,ErrorState,LoadingState} from "./Feedback";
import {navigate} from "../lib/router";

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
export function AllianceAnalytics({groupId,allianceId,allianceLabel}:{groupId:string;allianceId:string;allianceLabel:string}){
 const [days,setDays]=useState(30),[all,setAll]=useState(false),[kind,setKind]=useState<EventKind>("alliance_championship"),[query,setQuery]=useState(""),[limit,setLimit]=useState(50);
 const [data,setData]=useState<AnalyticsReport|null>(null),[error,setError]=useState("");
 useEffect(()=>{let live=true;setData(null);setError("");const p=period(days);api.analytics(groupId,all?"":allianceId,p.start,p.end).then(v=>{if(live)setData(v)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[groupId,allianceId,all,days]);
 const events=(data?.events??[]).filter(e=>e.event_type===kind).slice(-40);
 const players=(data?.players??[]).filter(p=>((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.trim().toLowerCase()));
 return <section className="data-panel analytics-panel"><div className="section-header"><div><h2>Alliance activity</h2><p>Published event evidence · independent dimensions</p></div><button className="button button--quiet" onClick={()=>navigate("/activity")}>Player activity →</button></div>
 <div className="activity-toolbar"><PeriodSelect days={days} onChange={setDays}/><label>Scope<select value={all?"all":"selected"} onChange={e=>setAll(e.target.value==="all")}><option value="selected">{allianceLabel}</option><option value="all">All alliances</option></select></label></div>
 {error?<ErrorState message={error}/>:!data?<LoadingState label="Loading alliance analytics"/>:!data.published_events?<EmptyState compact title="No published events in this period" description="Publish reviewed event results to populate charts and activity statistics."/>:<>
 <div className="analytics-summary"><div><small>Published events</small><strong>{data.published_events}</strong><span>{data.coverage.events_with_sessions} with session evidence</span></div>{(["alliance_championship","bear_trap","foundry","canyon"] as const).map(k=>{const c=eventCounts(data,k);return <div key={k}><small>{eventNames[k]} {k==="alliance_championship"?"registration":k==="bear_trap"?"attendance":"reliability"}</small><strong>{c?.rate==null?"—":c.rate+"%"}</strong><span>{c?.positive??0}/{c?.known??0} known · {c?.unknown??0} unknown</span></div>})}<div><small>Mobilization recorded points</small><strong>{formatTotal(data.events.some(e=>e.metrics.points?.total!=null)?data.events.reduce((n,e)=>n+BigInt(e.event_type==="alliance_mobilization"?e.metrics.points?.total??"0":"0"),0n).toString():null)}</strong><span>Recorded samples only</span></div></div>
 <details className="analytics-note"><summary>Data coverage</summary><p className="activity-explainer">Rates exclude unknown and excused outcomes; recorded rows are not a historical roster. {data.coverage.events_without_sessions} events without session evidence. {!all&&"Bear player-cycle records with unknown historical affiliation excluded: "+data.events.filter(e=>e.event_type==="bear_trap").reduce((n,e)=>n+e.unknown_home_players,0)+"."}</p></details>
 <div className="activity-toolbar"><label>Event type<select value={kind} onChange={e=>setKind(e.target.value as EventKind)}>{Object.entries(eventNames).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label></div>
 <div className="section-header"><div><h2>{eventNames[kind]} trend</h2><p>{kind==="alliance_mobilization"?"Average recorded points":kind==="alliance_championship"?"Registration among known outcomes":kind==="bear_trap"?"Attendance among known cycles":"Reliability among registered players with known attendance"}</p></div></div><TrendChart data={data} kind={kind}/>
 <div className="section-header"><div><h2>Activity heatmap</h2><p>Latest 40 events of selected type · one column per event</p></div></div>
 <p className="activity-explainer">{kind==="alliance_championship"?"Registration, not battle participation.":kind==="alliance_mobilization"?"Recorded results, not attendance.":kind==="bear_trap"?"One outcome per group Bear cycle.":"Attendance across recorded legions; mixed outcomes are retained."}</p>
 <div className="activity-toolbar"><label>Find player<input value={query} onChange={e=>{setQuery(e.target.value);setLimit(50)}} placeholder="Nickname or ID"/></label></div>
 <div className="analytics-legend">{Object.entries(heatLabels).map(([key,label])=><span key={key}><i className={"heat-"+key}/>{label}</span>)}</div>
 {!events.length?<EmptyState compact title="No events of this type" description="Select another event type or period."/>:!players.length?<EmptyState compact title="No matching players" description="Change the search filter."/>:<><div className="table-wrap analytics-heatmap"><table><thead><tr><th>Player</th>{events.map(e=><th key={e.id}><button className="table-link" title={e.occurred_on} onClick={()=>navigate("/events/"+encodeURIComponent(e.id))}>{e.occurred_on.slice(5)}</button></th>)}</tr></thead><tbody>{players.slice(0,limit).map(p=><tr key={p.fid}><td><button className="table-link" onClick={()=>navigate("/players/"+encodeURIComponent(p.fid))}>{p.nickname??p.fid}</button></td>{events.map(e=>{const cell=heatCell(e,p.fid);return <td key={e.id}><span className={"heat-cell heat-"+cell} title={heatLabels[cell]} aria-label={heatLabels[cell]}>{heatMarks[cell]}</span></td>})}</tr>)}</tbody></table></div>{players.length>limit&&<button className="button button--quiet analytics-more" onClick={()=>setLimit(n=>n+50)}>Load more ({limit} of {players.length})</button>}</>}
 </>}</section>
}
