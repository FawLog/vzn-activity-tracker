import {useEffect,useRef,useState} from "react";
import {api} from "../lib/api";
import {allowNavigation,useNavigationGuard} from "../lib/navigation-guard";
import {creationEventOptions} from "../lib/calendar-event-options";
import {gameEventForCalendar} from "../lib/game-event-catalog";
import type {Alliance} from "../lib/types";
import {calendarEndLabel,type CalendarOccurrence} from "../lib/calendar";

type Props={eventType:string;groupId:string;alliances:Alliance[];preferred?:string;day:string;onEvent:(type:string)=>void;onManual:()=>void;onClose:()=>void;onSaved:(day:string)=>void};
type Plan={active_rule_id:string|null;active_from:string|null;items:CalendarOccurrence[]};
export function FollowScheduleEditor({eventType,groupId,alliances,preferred,day,onEvent,onManual,onClose,onSaved}:Props){
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const defaultState=(active.find(a=>a.id===preferred)??active[0])?.state_id??"";
  const [stateId,setStateId]=useState(defaultState);
  const [start,setStart]=useState(day);
  const [plan,setPlan]=useState<Plan|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [retry,setRetry]=useState(0);
  const lock=useRef(false);
  const event=gameEventForCalendar(eventType)!;
  const parent=event.scheduleDependency?.label??"parent event";
  useNavigationGuard(stateId!==defaultState||start!==day,busy);
  useEffect(()=>{
    setPlan(null);setError("");
    if(!stateId||!start)return;
    const controller=new AbortController();
    api.previewFollow(groupId,eventType,stateId,start,controller.signal).then(p=>{if(!controller.signal.aborted)setPlan(p);})
      .catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:"Unable to preview schedule");});
    return ()=>controller.abort();
  },[groupId,eventType,stateId,start,retry]);
  async function save(){
    if(lock.current||!plan||plan.active_rule_id||!stateId||!start)return;
    lock.current=true;setBusy(true);setError("");
    try{const result=await api.enableFollow(groupId,eventType,stateId,start);onSaved(result.items[0]?.starts_at??start);}
    catch(e){setError(e instanceof Error?e.message:"Unable to save follow rule");}
    finally{lock.current=false;setBusy(false);}
  }
  async function stop(){
    if(lock.current||!plan?.active_rule_id||!window.confirm("Stop following the parent event? Past and already-started dates remain visible."))return;
    lock.current=true;setBusy(true);setError("");
    try{await api.stopFollow(groupId,plan.active_rule_id);setRetry(n=>n+1);}
    catch(e){setError(e instanceof Error?e.message:"Unable to stop follow rule");}
    finally{lock.current=false;setBusy(false);}
  }
  return <section className="data-panel calendar-editor" aria-label="Schedule editor">
    <h2>Add event</h2><p>{event.name} follows {parent} in the game.</p>
    <div className="calendar-editor-fields">
      <label>Event type<select disabled={busy} value={eventType} onChange={e=>onEvent(e.target.value)}>{creationEventOptions.map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
      <label>State<select value={stateId} disabled={busy} onChange={e=>{setPlan(null);setStateId(e.target.value);}}>{[...new Set(active.map(a=>a.state_id))].map(s=><option key={s} value={s}>State #{s}</option>)}</select></label>
      <label>Follow starting from (UTC)<input type="date" value={start} disabled={busy} onChange={e=>{setPlan(null);setStart(e.target.value);}}/></label>
      <strong>Follow {parent} automatically</strong>
      <p>{event.duration}. Dates update with the parent schedule. Future dates are estimated, not game-confirmed.</p>
    </div>
    {plan?<div className="calendar-series-preview">
      {plan.active_rule_id&&<p role="status">Already following since {plan.active_from}.</p>}
      <h3>Next 60 days</h3>
      {plan.items.length?<ul>{plan.items.map(r=><li key={r.id}>{r.starts_at} — {calendarEndLabel(r.ends_at,r.precision)} · {r.schedule_status==="cancelled"?"Cancelled":"Estimated"}</li>)}</ul>:<p>No matching state-level parent schedule in this period. Events appear automatically when the parent is scheduled.</p>}
      {plan.active_rule_id?<button type="button" className="button button--quiet" disabled={busy} onClick={()=>void stop()}>Stop following</button>:<button type="button" className="button button--primary" disabled={busy||!start||!stateId} onClick={()=>void save()}>Save schedule</button>}
    </div>:!error&&<p>Loading matching parent dates…</p>}
    {error&&<p role="alert">{error}</p>}
    <div className="calendar-controls"><button type="button" className="button button--quiet" disabled={busy||!!plan?.active_rule_id} onClick={onManual}>Set independent dates</button><button type="button" className="button button--quiet" disabled={busy} onClick={()=>{if(allowNavigation())onClose();}}>Close editor</button></div>
  </section>;
}
