import { useNavigationGuard } from "../lib/navigation-guard";
import {useState,useRef} from "react";
import {api,type CalendarEventLinkState} from "../lib/api";
import type {CalendarOccurrence} from "../lib/calendar";

export function CalendarSessionGrouping({groupId,row,data,writable,blocked,onSaved,onEditingChange}:{groupId:string;row:CalendarOccurrence;data:CalendarEventLinkState;writable:boolean;blocked:boolean;onSaved:(result:CalendarEventLinkState)=>void;onEditingChange:(blocked:boolean)=>void}){
  const bear=row.event_type==="bear_trap";
  const [day,setDay]=useState(data.entry_cycle_date??"");
  const [session,setSession]=useState(data.entry_session_key??"");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const lock=useRef(false);
  useNavigationGuard(day!==(data.entry_cycle_date??"")||session!==(data.entry_session_key??""),busy);
  async function save(clear=false){
    if(lock.current)return;lock.current=true;setBusy(true);onEditingChange(true);setError("");
    try{onSaved(await api.setCalendarEntryGrouping(groupId,row.id,data.revision,clear?null:day,clear?null:session));}
    catch(e){setError(e instanceof Error?e.message:"Unable to save grouping");}
    finally{lock.current=false;setBusy(false);onEditingChange(false);}
  }
  return <section className="calendar-stage-timeline" aria-label="Session grouping">
    <h4>{bear?"Group Bear cycle":"Battle session grouping"}</h4>
    <p>{data.entry_cycle_date?"Cycle "+data.entry_cycle_date+" · "+data.entry_session_key?.replaceAll("_"," "):"No explicit grouping. Choose the same cycle date for related schedules."}</p>
    {!!data.group_members?.length&&<ul>{data.group_members.map(s=><li key={s.id}>{s.tag} · {s.entry_session_key.replaceAll("_"," ")} · {s.starts_at} · {s.linked?"Record linked":"Planned only"}</li>)}</ul>}
    {writable&&!data.linked&&<div className="calendar-editor-fields">
      <label>Shared cycle date (UTC)<input type="date" value={day} disabled={busy||blocked} onChange={e=>setDay(e.target.value)}/></label>
      <label>{bear?"Unique trap within group cycle":"Legion identity"}<select value={session} disabled={busy||blocked} onChange={e=>setSession(e.target.value)}><option value="">Choose explicitly</option>{Array.from({length:bear?30:2},(_,i)=><option key={i} value={(bear?"trap_":"legion_")+(i+1)}>{bear?"Trap ":"Legion "}{i+1}</option>)}</select></label>
      <button className="button button--primary" disabled={busy||blocked||!day||!session} onClick={()=>void save()}>Save grouping</button>
      {data.entry_cycle_date&&<button className="button button--quiet" disabled={busy||blocked} onClick={()=>void save(true)}>Clear grouping</button>}
    </div>}
    {error&&<p role="alert">{error}</p>}
    <small>Grouping does not create actual events or results. Use the same reviewed cycle date for related schedules; trap identifiers must be unique across alliances.</small>
  </section>;
}
