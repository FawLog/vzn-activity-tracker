import {useState,useRef} from "react";
import {api,type CalendarEventLinkState} from "../lib/api";
import type {CalendarOccurrence} from "../lib/calendar";
import type {EventRecord} from "../lib/types";

export function CalendarDraftEditor({groupId,row,data,onCreated}:{groupId:string;row:CalendarOccurrence;data:CalendarEventLinkState;onCreated:(result:CalendarEventLinkState)=>void}){
  const bear=row.event_type==="bear_trap";
  const session=bear||["foundry","canyon"].includes(row.event_type);
  const [cycle,setCycle]=useState("");
  const [cycles,setCycles]=useState<{date:string;items:Pick<EventRecord,"id"|"status"|"occurred_on">[]}|null>(null);
  const [eventId,setEventId]=useState(data.linked?.id??"");
  const [key,setKey]=useState("");
  const [review,setReview]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const lock=useRef(false);
  const choices=bear?(cycles?.date===cycle?cycles.items:[]):data.items;
  const existing=data.linked?[data.linked]:choices;
  const canCreate=(!bear||cycles?.date===cycle)&&(!existing.length||existing.some(e=>e.id===eventId&&e.status==="draft"))&&(!session||!!key)&&review;
  async function lookup(){
    if(lock.current)return;lock.current=true;setBusy(true);setError("");setReview(false);setCycles(null);setEventId("");
    try{const r=await api.calendarBearCycles(groupId,row.id,cycle);setCycles({date:cycle,items:r.items});}
    catch(e){setError(e instanceof Error?e.message:"Unable to check cycles");}finally{lock.current=false;setBusy(false);}
  }
  async function save(){
    if(lock.current||!canCreate)return;lock.current=true;setBusy(true);setError("");
    try{const r=await api.createCalendarDraft(groupId,row.id,{revision:data.revision,confirmed:true,...(eventId?{event_id:eventId}:{}),...(bear?{cycle_date:cycle}:{}),...(session?{session_key:key}:{})});onCreated(r);}
    catch(e){setError(e instanceof Error?e.message:"Unable to create draft");}finally{lock.current=false;setBusy(false);}
  }
  if(row.confidence!=="confirmed")return <p>Confirm the schedule before creating a draft record.</p>;
  if(session&&row.precision!=="minute")return <p>Set the exact UTC session time before creating a draft session.</p>;
  if(!session&&(data.linked||choices.length))return null;
  if(data.truncated)return <p>Too many matching records; review Events before creating a draft.</p>;
  return <details><summary>Create draft from calendar</summary>
    <p>Uses the saved alliance and UTC schedule. Creates a draft only, with no participants or results.</p>
    <fieldset disabled={busy} className="calendar-editor-fields">
      {bear&&<><label>Group Bear cycle date (UTC)<input type="date" value={cycle} onChange={e=>{setCycle(e.target.value);setCycles(null);setEventId("");setReview(false);}}/></label><button type="button" className="button button--quiet" disabled={!cycle} onClick={()=>void lookup()}>Check Bear cycle</button></>}
      {(!bear||cycles?.date===cycle)&&<>{existing.length?<label>Existing draft event<select value={eventId} disabled={!!data.linked} onChange={e=>{setEventId(e.target.value);setReview(false);}}><option value="">Choose existing record</option>{existing.map(e=><option key={e.id} value={e.id} disabled={e.status!=="draft"}>{e.occurred_on} · {e.status} · {e.id.slice(0,12)}</option>)}</select></label>:<p>No event on the selected cycle date. A new draft will be created.</p>}
      {session&&<label>{bear?"Unique trap identifier within group cycle":"Legion"}<select value={key} onChange={e=>{setKey(e.target.value);setReview(false);}}><option value="">Choose explicitly</option>{Array.from({length:bear?30:2},(_,i)=><option key={i} value={(bear?"trap_":"legion_")+(i+1)}>{bear?"Trap ":"Legion "}{i+1}</option>)}</select></label>}
      <label className="calendar-checkbox"><input type="checkbox" checked={review} onChange={e=>setReview(e.target.checked)}/>I reviewed the owner, date and session identity</label></>}
    </fieldset>
    {error&&<p role="alert">{error}</p>}
    <button type="button" className="button button--primary" disabled={busy||!canCreate} onClick={()=>void save()}>Create linked draft</button>
  </details>;
}
