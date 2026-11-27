import {useState} from "react";
import type {Alliance,ManualEvent,Player} from "../lib/types";
import {foundryRegistrationPreview} from "../lib/foundryRegistration";
type Completion={revisions:Record<string,number>;roster:string[];home_alliances?:Record<string,string>;excused:string[];no_duty:string[];expected_sessions:number};
export function AttendanceFinalReview({event,candidates,alliances,allianceId,occurredOn,disabled,onPublish}:{event:ManualEvent;candidates:Player[];alliances:Alliance[];allianceId:string;occurredOn:string;disabled:boolean;onPublish:(value:Completion)=>void}){
 const bear=event.event_type==="bear_trap";
 const foundry=event.event_type==="foundry";
 const canyon=event.event_type==="canyon";
 const legionBattle=foundry||canyon;
 const isPresent=(r:ManualEvent["sessions"][number]["rows"][number])=>foundry?(r.metrics.personal_points??0)>0:r.attendance==="confirmed_present"||(r.metrics.damage??0)>0||(r.metrics.personal_points??0)>0;
 const present=new Set(event.sessions.flatMap(s=>s.rows.filter(isPresent).map(r=>r.fid)));
 const prior=event.completion??[];
 const historical=event.historical_homes??{};
 const hostIds=new Set(event.sessions.map(s=>s.host_alliance_id??allianceId));
 const suggested=candidates.filter(p=>legionBattle?(historical[p.fid]===allianceId||!historical[p.fid]&&p.group_status==="active"&&p.primary_alliance_id===allianceId):p.group_status==="active"&&(bear?hostIds.has(historical[p.fid]??p.primary_alliance_id??""):p.primary_alliance_id===allianceId)).map(p=>p.fid);
 const initialRoster=bear?[...new Set([...prior.filter(r=>r.roster_member).map(r=>r.fid),...suggested])]:prior.length?prior.filter(r=>r.roster_member).map(r=>r.fid):suggested;
 const [homes,setHomes]=useState<Record<string,string>>(()=>({...historical}));
 const [roster,setRoster]=useState<string[]>(()=>legionBattle?[...new Set([...initialRoster,...event.sessions.flatMap(s=>s.rows.filter(r=>r.registration==="registered").map(r=>r.fid))])]:initialRoster);
 const [excused,setExcused]=useState<string[]>(prior.filter(r=>r.outcome==="excused").map(r=>r.fid));
 const [noDuty,setNoDuty]=useState<string[]>(prior.filter(r=>r.outcome==="no_duty").map(r=>r.fid));
 const [query,setQuery]=useState("");
 const [expected,setExpected]=useState(bear?String(prior.length?event.sessions.length:3):"2");
 const [confirmed,setConfirmed]=useState(false);

 const eligible=new Set(roster);
 const exceptions=excused.filter(f=>eligible.has(f)&&!present.has(f));
 const ineligible=noDuty.filter(f=>eligible.has(f)&&!present.has(f));
 const absent=roster.filter(f=>!present.has(f)&&!exceptions.includes(f)&&!ineligible.includes(f));
 const registration=legionBattle?foundryRegistrationPreview(event.sessions,roster,[...exceptions,...ineligible]):null;
 const valid=Number.isInteger(Number(expected))&&Number(expected)>0&&Number(expected)<=30&&event.sessions.length===Number(expected)&&event.sessions.every(s=>s.rows.length>0)&&roster.length>0&&(!bear||roster.every(f=>!!homes[f]))&&(!foundry||event.sessions.every(s=>s.registration_complete&&s.results_complete))&&(!canyon||event.sessions.every(s=>s.registration_complete&&s.attendance_complete));
 const toggle=(f:string,values:string[],set:(v:string[])=>void)=>{set(values.includes(f)?values.filter(x=>x!==f):[...values,f]);setConfirmed(false)};
 return <div className="manual-review">
  <h3>Final attendance review</h3>
  <p>One event, one attendance outcome. Confirm the complete event-date roster ({occurredOn}) and {foundry?"both complete result lists. Explicit zero means no-show for a selected player; missing points are unknown.":"all actual participants, including zero-point attendees."} Current home roster is only a starting point.</p>
  <div className="manual-controls"><label>Expected {bear?"traps":"legions"}<input type="number" min={1} max={30} value={expected} disabled={disabled||!bear} onChange={e=>{setExpected(e.target.value);setConfirmed(false)}}/></label><span>{event.sessions.length} recorded</span><span>{new Set([...roster,...present]).size} reviewed · {present.size} present · {exceptions.length} excused · {ineligible.length} no duty · {(legionBattle&&event.sessions.length!==2)||(foundry&&!event.sessions.every(s=>s.registration_complete&&s.results_complete))||(canyon&&!event.sessions.every(s=>s.registration_complete&&s.attendance_complete))?"Attendance pending":absent.length+" absent if confirmed"}</span></div>
  {registration&&<div className="manual-review"><h4>Cycle registration preview</h4><p>{["legion_1","legion_2"].map(key=>{const s=event.sessions.find(x=>x.session_key===key);return key.replace("_"," ")+": "+(!s?"not recorded":s.registration_complete?"verified":"pending verification")}).join(" · ")}</p><p role="status">{registration.registered.length} registered · {registration.notRegistered.length} not registered · {registration.unknown.length} unknown · {registration.excluded.length} excused / no duty</p><p>{registration.complete?"Both registration lists verified. Eligible players missing from both lists are automatically not registered; no individual marking is needed.":"Both registration lists must be saved and verified before unlisted players become not registered."} This is a draft preview based on the proposed event-date roster, not published activity.</p>{registration.complete&&<details><summary>Not registered ({registration.notRegistered.length})</summary><p>{registration.notRegistered.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")||"None"}</p></details>}</div>}
  {foundry&&<p>{event.sessions.every(s=>s.registration_complete&&s.results_complete)&&event.sessions.length===2?"Both legions reviewed.":"Confirm registration and personal results for both legions before finalizing."}</p>}
  <p>{event.sessions.map(s=>s.session_key.replaceAll("_"," ")+": "+s.rows.filter(isPresent).length+" present").join(" · ")}</p>
  {bear&&<div className="manual-controls"><p>Review both host rosters. Historical homes are locked; explicitly assign uncertain homes before publishing.</p>{alliances.map(a=><span key={a.id}>{a.name}: {roster.filter(f=>homes[f]===a.id).length} eligible</span>)}<span>Unconfirmed home: {roster.filter(f=>!homes[f]).length}</span></div>}
  {bear&&[...new Set([...roster,...present])].filter(f=>!historical[f]).map(f=><label key={f}>{candidates.find(p=>p.fid===f)?.nickname??f} · reviewed home<select aria-label={f+" reviewed home"} value={homes[f]??""} disabled={disabled} onChange={e=>{setHomes(v=>({...v,[f]:e.target.value}));setConfirmed(false)}}><option value="">Confirm home</option>{alliances.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>)}
  <label>Find roster exceptions<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Nickname or FID"/></label>
  {query.trim()&&<div className="table-wrap"><table><thead><tr><th>Player</th><th>Event roster</th><th>Excused</th><th>No duty</th></tr></thead><tbody>{candidates.filter(p=>((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.toLowerCase())).slice(0,30).map(p=><tr key={p.fid}><td>{p.nickname??p.fid}</td><td><input type="checkbox" aria-label={p.fid+" in event roster"} checked={eligible.has(p.fid)} disabled={disabled||present.has(p.fid)} onChange={e=>{setRoster(v=>e.target.checked?[...new Set([...v,p.fid])]:v.filter(f=>f!==p.fid));setConfirmed(false)}}/></td><td><input type="checkbox" aria-label={p.fid+" excused"} checked={exceptions.includes(p.fid)} disabled={disabled||!eligible.has(p.fid)||present.has(p.fid)} onChange={()=>{toggle(p.fid,excused,setExcused);setNoDuty(v=>v.filter(f=>f!==p.fid))}}/></td><td><input type="checkbox" aria-label={p.fid+" no duty"} checked={ineligible.includes(p.fid)} disabled={disabled||!eligible.has(p.fid)||present.has(p.fid)} onChange={()=>{toggle(p.fid,noDuty,setNoDuty);setExcused(v=>v.filter(f=>f!==p.fid))}}/></td></tr>)}</tbody></table></div>}
  <details><summary>Review event roster ({roster.length})</summary><p>{roster.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")}</p></details>
  {(!legionBattle||event.sessions.length===2&&event.sessions.every(s=>s.registration_complete&&(foundry?s.results_complete:s.attendance_complete)))&&<details><summary>Would be absent ({absent.length})</summary><p>{absent.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")}</p></details>}
  <p>Excused: {exceptions.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")||"None"} · No duty: {ineligible.map(f=>candidates.find(p=>p.fid===f)?.nickname??f).join(", ")||"None"}</p>
  <label><input type="checkbox" checked={confirmed} disabled={disabled||!valid} onChange={e=>setConfirmed(e.target.checked)}/>I verified the full event-date roster and attendance for every expected session. Mark all other eligible players absent.</label>
  <button className="button button--primary" disabled={disabled||!valid||!confirmed} onClick={()=>onPublish({revisions:Object.fromEntries(event.sessions.map(s=>[s.id,s.revision])),roster,...(bear?{home_alliances:Object.fromEntries([...new Set([...roster,...present])].filter(f=>!!homes[f]).map(f=>[f,homes[f]]))}:{}),excused:exceptions,no_duty:ineligible,expected_sessions:Number(expected)})}>Finalize and publish</button>
 </div>
}
