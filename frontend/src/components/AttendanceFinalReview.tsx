import {useState} from "react";
import type {ManualEvent,Player} from "../lib/types";
type Completion={revisions:Record<string,number>;roster:string[];excused:string[];no_duty:string[];expected_sessions:number};
export function AttendanceFinalReview({event,candidates,allianceId,occurredOn,disabled,onPublish}:{event:ManualEvent;candidates:Player[];allianceId:string;occurredOn:string;disabled:boolean;onPublish:(value:Completion)=>void}){
 const bear=event.event_type==="bear_trap";
 const isPresent=(r:ManualEvent["sessions"][number]["rows"][number])=>r.attendance==="confirmed_present"||(r.metrics.damage??0)>0||(r.metrics.personal_points??0)>0;
 const present=new Set(event.sessions.flatMap(s=>s.rows.filter(isPresent).map(r=>r.fid)));
 const [added,setAdded]=useState<string[]>([]);
 const [excluded,setExcluded]=useState<string[]>([]);
 const [excused,setExcused]=useState<string[]>([]);
 const [noDuty,setNoDuty]=useState<string[]>([]);
 const [query,setQuery]=useState("");
 const [expected,setExpected]=useState(bear?"3":"2");
 const [confirmed,setConfirmed]=useState(false);
 const roster=[...new Set([...candidates.filter(p=>p.primary_alliance_id===allianceId&&p.group_status==="active").map(p=>p.fid),...added])].filter(f=>!excluded.includes(f));
 const eligible=new Set(roster);
 const exceptions=excused.filter(f=>eligible.has(f)&&!present.has(f));
 const ineligible=noDuty.filter(f=>eligible.has(f)&&!present.has(f));
 const absent=roster.filter(f=>!present.has(f)&&!exceptions.includes(f)&&!ineligible.includes(f));
 const valid=Number.isInteger(Number(expected))&&Number(expected)>0&&Number(expected)<=30&&event.sessions.length===Number(expected)&&event.sessions.every(s=>s.rows.length>0)&&roster.length>0;
 const toggle=(f:string,values:string[],set:(v:string[])=>void)=>{set(values.includes(f)?values.filter(x=>x!==f):[...values,f]);setConfirmed(false)};
 return <div className="manual-review">
  <h3>Final attendance review</h3>
  <p>One event, one attendance outcome. Confirm the complete event-date roster ({occurredOn}) and all actual participants, including zero-point attendees. Current home roster is only a starting point.</p>
  <div className="manual-controls"><label>Expected {bear?"traps":"legions"}<input type="number" min={1} max={30} value={expected} disabled={disabled||!bear} onChange={e=>{setExpected(e.target.value);setConfirmed(false)}}/></label><span>{event.sessions.length} recorded</span><span>{roster.length} roster · {present.size} present · {exceptions.length} excused · {ineligible.length} no duty · {absent.length} absent if confirmed</span></div>
  <p>{event.sessions.map(s=>s.session_key.replaceAll("_"," ")+": "+s.rows.filter(isPresent).length+" present").join(" · ")}</p>
  <label>Find roster exceptions<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Nickname or FID"/></label>
  {query.trim()&&<div className="table-wrap"><table><thead><tr><th>Player</th><th>Event roster</th><th>Excused</th><th>No duty</th></tr></thead><tbody>{candidates.filter(p=>((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.toLowerCase())).slice(0,30).map(p=><tr key={p.fid}><td>{p.nickname??p.fid}</td><td><input type="checkbox" aria-label={p.fid+" in event roster"} checked={eligible.has(p.fid)} disabled={disabled||present.has(p.fid)} onChange={e=>{if(e.target.checked){setExcluded(v=>v.filter(f=>f!==p.fid));setAdded(v=>[...v,p.fid])}else{setExcluded(v=>[...v,p.fid]);setAdded(v=>v.filter(f=>f!==p.fid))}setConfirmed(false)}}/></td><td><input type="checkbox" aria-label={p.fid+" excused"} checked={exceptions.includes(p.fid)} disabled={disabled||!eligible.has(p.fid)||present.has(p.fid)} onChange={()=>{toggle(p.fid,excused,setExcused);setNoDuty(v=>v.filter(f=>f!==p.fid))}}/></td><td><input type="checkbox" aria-label={p.fid+" no duty"} checked={ineligible.includes(p.fid)} disabled={disabled||!eligible.has(p.fid)||present.has(p.fid)} onChange={()=>{toggle(p.fid,noDuty,setNoDuty);setExcused(v=>v.filter(f=>f!==p.fid))}}/></td></tr>)}</tbody></table></div>}
  <p>Excused: {exceptions.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")||"None"} · No duty: {ineligible.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")||"None"}</p>
  <label><input type="checkbox" checked={confirmed} disabled={disabled||!valid} onChange={e=>setConfirmed(e.target.checked)}/>I verified the full event-date roster and attendance for every expected session. Mark all other eligible players absent.</label>
  <button className="button button--primary" disabled={disabled||!valid||!confirmed} onClick={()=>onPublish({revisions:Object.fromEntries(event.sessions.map(s=>[s.id,s.revision])),roster,excused:exceptions,no_duty:ineligible,expected_sessions:Number(expected)})}>Finalize and publish</button>
 </div>
}
