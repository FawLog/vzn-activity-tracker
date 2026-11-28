import {useEffect,useRef,useState} from "react";
import {api,type CalendarEventLinkState} from "../lib/api";
import {navigate} from "../lib/router";
import type {CalendarOccurrence} from "../lib/calendar";
import {CalendarDraftEditor} from "./CalendarDraftEditor";
import {CalendarReviewPanel} from "./CalendarReviewPanel";
import {CalendarEventWorkspace} from "./CalendarEventWorkspace";
import {CalendarSessionGrouping} from "./CalendarSessionGrouping";
import {formatDate} from "../lib/format";

export function CalendarEventLink({groupId,row,writable,onRevision,onEditingChange,workspaceBlocked}:{groupId:string;row:CalendarOccurrence;writable:boolean;onRevision:(revision:number)=>void;onEditingChange:(blocked:boolean)=>void;workspaceBlocked:boolean}){
  const [data,setData]=useState<CalendarEventLinkState|null>(null);
  const [choice,setChoice]=useState("");
  const [sessionChoice,setSessionChoice]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    api.calendarEventLink(groupId,row.id,controller.signal).then(result=>{if(!controller.signal.aborted)setData(result);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[groupId,row.id,refresh]);
  async function save(id:string|null,sessionId?:string){
    if(!data||lock.current)return;
    lock.current=true;setBusy(true);setError("");
    try{const result=await api.setCalendarEventLink(groupId,row.id,id,data.revision,sessionId);setData(result);setChoice("");setSessionChoice("");onRevision(result.revision);}
    catch(e){setError(e instanceof Error?e.message:"Unable to update link");}finally{lock.current=false;setBusy(false);}
  }
  async function start(){
    if(!data||lock.current)return;
    lock.current=true;setBusy(true);onEditingChange(true);setError("");
    try{const result=await api.startCalendarEntry(groupId,row.id,data.revision);setData(result);onRevision(result.revision);}
    catch(e){setError(e instanceof Error?e.message:"Unable to start data entry");}
    finally{lock.current=false;setBusy(false);onEditingChange(false);}
  }
  const needsSession=["bear_trap","foundry","canyon"].includes(row.event_type);
  const ready=!!data?.linked&&(!needsSession||!!data.linked.session_id);
  return <section className="calendar-stage-timeline" aria-label="Actual event record">
    <h3>Event data</h3>
    <p>Planning and results remain independent. Linking does not create attendance or change statistics.</p>
    {error&&<p role="alert">{error}</p>}
    {!data&&!error&&<p>Loading matching records…</p>}
    {data?.eligible&&needsSession&&<CalendarSessionGrouping key={row.id+":"+data.revision} groupId={groupId} row={row} data={data} writable={writable} blocked={workspaceBlocked||busy} onEditingChange={onEditingChange} onSaved={result=>{setData(result);onRevision(result.revision);}}/>}
    {writable&&data?.eligible&&!ready&&row.confidence==="confirmed"&&(row.event_type!=="bear_trap"||!!data.entry_cycle_date)&&(!needsSession||row.precision==="minute")&&<div className="calendar-controls"><button className="button button--primary" disabled={busy||workspaceBlocked} onClick={()=>void start()}>Enter event data</button><small>Reuses a matching record or prepares a draft when the identity is clear.</small></div>}
    {data?.linked?<><p>Linked · {data.linked.status} · {formatDate(data.linked.occurred_on)}{data.linked.session_key?" · "+data.linked.session_key.replaceAll("_"," ")+" · "+data.linked.started_at:""}</p><div className="calendar-controls"><button className="button button--primary" disabled={workspaceBlocked} onClick={()=>navigate("/events/"+encodeURIComponent(data.linked!.id))}>Open event history</button>{writable&&<button className="button button--quiet" disabled={busy||workspaceBlocked} onClick={()=>void save(null)}>Unlink event</button>}</div></>:
      data?.eligible&&!data.entry_cycle_date?<>{data.items.length?<><label>Matching actual event<select value={choice} disabled={busy||!writable} onChange={e=>setChoice(e.target.value)}><option value="">Choose explicitly</option>{data.items.map(item=><option key={item.id} value={item.id}>{formatDate(item.occurred_on)} · {item.status} · {item.id.slice(0,12)}</option>)}</select></label>{writable&&<button className="button button--quiet" disabled={!choice||busy} onClick={()=>void save(choice)}>Link selected event</button>}</>:<p>No matching event-level record. Check available sessions below. Missing records do not mean the event was missed.</p>}{data.truncated&&<p>Only the first 100 matches are shown.</p>}</>:data&&!data.eligible?<p>Linking is not supported for this schedule type or phase yet.</p>:null}
    {data?.eligible&&!data.entry_cycle_date&&!data.linked?.session_id&&["bear_trap","foundry","canyon"].includes(row.event_type)&&<div className="calendar-editor-fields">
      <h4>Specific trap or legion</h4>
      {data.sessions.length?<><label>Matching actual session<select disabled={busy||!writable} value={sessionChoice} onChange={e=>setSessionChoice(e.target.value)}><option value="">Choose explicitly</option>{data.sessions.map(s=><option key={s.id} value={s.id}>{s.session_key.replaceAll("_"," ")} · {s.started_at} · {s.status} · cycle {s.occurred_on}</option>)}</select></label>
      {writable&&<button className="button button--primary" disabled={busy||!sessionChoice} onClick={()=>{const s=data.sessions.find(x=>x.id===sessionChoice);if(s)void save(s.event_id,s.id);}}>Link selected session</button>}</>:<p>No matching unlinked session. Verify host and UTC date/time in Events.</p>}
    </div>}
    {data?.review&&<CalendarReviewPanel review={data.review}/>}
    {data?.linked&&writable&&(!["bear_trap","foundry","canyon"].includes(row.event_type)||data.linked.session_id)&&<CalendarEventWorkspace key={groupId+":"+data.linked.id+":"+(data.linked.session_id??"main")} groupId={groupId} eventId={data.linked.id} sessionId={data.linked.session_id} onEditingChange={onEditingChange} onRefresh={()=>{setRefresh(n=>n+1);onRevision(data.revision);}}/>}
    {writable&&data?.eligible&&!data.entry_cycle_date&&!data.linked?.session_id&&<CalendarDraftEditor key={row.id+":"+data.revision} groupId={groupId} row={row} data={data} onCreated={result=>{setData(result);onRevision(result.revision);}}/>}
  </section>;
}
export function EventCalendarLinks({groupId,eventId}:{groupId:string;eventId:string}){
  const [items,setItems]=useState<(CalendarOccurrence&{linked_session_id?:string|null})[]|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    api.eventSchedules(groupId,eventId,controller.signal).then(r=>{if(!controller.signal.aborted)setItems(r.items);}).catch(()=>{if(!controller.signal.aborted)setError("Unable to load linked schedules");});
    return ()=>controller.abort();
  },[groupId,eventId]);
  return <section className="data-panel calendar-stage-timeline" aria-label="Linked calendar schedules"><h3>Linked calendar schedules</h3>{error?<p role="alert">{error}</p>:items===null?<p>Loading schedules…</p>:items.length?<ul>{items.map(row=><li key={row.id}><button className="button button--quiet" onClick={()=>navigate("/calendar?day="+encodeURIComponent(row.starts_at.slice(0,10))+"&occurrence="+encodeURIComponent(row.id))}>{row.starts_at} · {row.phase||"Schedule"} · {row.confidence}{row.linked_session_id?" · Session linked":""}</button></li>)}</ul>:<p>No linked schedules.</p>}</section>;
}
