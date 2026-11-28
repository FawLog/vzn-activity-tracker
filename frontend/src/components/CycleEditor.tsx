import { allowNavigation, useNavigationGuard } from "../lib/navigation-guard";
import {useEffect,useRef,useState} from "react";
import {api} from "../lib/api";
import {cycleDraft,type CycleKind} from "../lib/calendar-cycles";
import {weekStart,type CalendarOccurrence} from "../lib/calendar";
import {serializeTime,utcInput,type ScheduleFields} from "../lib/schedule-editor";
import type {Alliance} from "../lib/types";
type Props={groupId:string;alliances:Alliance[];preferred?:string;day:string;onClose:()=>void;onSaved:(day:string)=>void};
export function CycleEditor({groupId,alliances,preferred,day,onClose,onSaved}:Props){
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const [kind,setKind]=useState<CycleKind>("canyon");
  const [owner,setOwner]=useState(active.find(a=>a.id===preferred)?.id??active[0]?.id??"");
  const [anchor,setAnchor]=useState(weekStart(day));
  const [phases,setPhases]=useState<ScheduleFields[]>([]);
  const [review,setReview]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  const request=useRef<{fingerprint:string;key:string}|null>(null);
  const fingerprint=JSON.stringify({kind,owner,anchor,phases});
  const initial=useRef(fingerprint);
  useNavigationGuard(initial.current!==fingerprint,busy);
  const invalidate=()=>{setPhases([]);setReview("");setError("");};
  function preview(){
    try{
      const a=active.find(a=>a.id===owner);
      if(!a)throw Error("Choose an active alliance");
      setPhases(cycleDraft(kind,anchor,a.state_id,a.id));setReview("");setError("");
    }catch(e){setError(e instanceof Error?e.message:"Unable to preview");}
  }
  function patch(index:number,next:Partial<ScheduleFields>){
    setPhases(old=>old.map((p,i)=>i===index?{...p,...next}:p));setReview("");
  }
  async function save(){
    if(lock.current||review!==fingerprint||!phases.length)return;
    lock.current=true;setBusy(true);setError("");
    try{
      if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
      const result=await api.createCycle(groupId,{kind,phases,request_key:request.current.key});
      onSaved(result.items[0].starts_at.slice(0,10));
    }catch(e){setError(e instanceof Error?e.message:"Unable to save cycle");}
    finally{lock.current=false;setBusy(false);}
  }
  return <section className="data-panel calendar-editor" aria-label="Cycle editor">
    <h2>Plan event cycle</h2><p>Review every phase. This creates linked calendar entries only, never actual event results.</p>
    <fieldset disabled={busy} className="calendar-editor-fields">
      <label>Cycle type<select value={kind} onChange={e=>{setKind(e.target.value as CycleKind);invalidate();}}><option value="canyon">Canyon Clash</option><option value="svs">SvS</option></select></label>
      <label>{kind==="svs"?"State (via active alliance)":"Alliance"}<select value={owner} onChange={e=>{setOwner(e.target.value);invalidate();}}>{active.map(a=><option key={a.id} value={a.id}>{a.tag} · #{a.state_id}</option>)}</select></label>
      <label>Monday anchor (UTC)<input type="date" value={anchor} onChange={e=>{setAnchor(e.target.value);invalidate();}}/></label>
      <button type="button" className="button button--quiet" onClick={preview}>Preview cycle</button>
    </fieldset>
    {!!phases.length&&<div className="calendar-series-preview">
      <p>Source: whiteout-survival-data 0.11.0. All suggested dates are estimated. Canyon battle time is unknown; SvS preparation duration is inconsistent in the source, so review the extended fifth day.</p>
      {phases.map((p,i)=><fieldset key={p.phase} disabled={busy} className="calendar-editor-fields"><legend>{p.phase}</legend>
        <label>Precision<select value={p.precision} onChange={e=>{const precision=e.target.value as ScheduleFields["precision"];patch(i,{precision,starts_at:precision==="date"?p.starts_at.slice(0,10):"",ends_at:null});}}><option value="date">Date only</option><option value="minute">UTC time</option></select></label>
        <label>Starts (UTC)<input type={p.precision==="date"?"date":"datetime-local"} value={utcInput(p.starts_at,p.precision)} onChange={e=>patch(i,{starts_at:e.target.value?serializeTime(e.target.value,p.precision):""})}/></label>
        <label>Ends (optional, exclusive)<input type={p.precision==="date"?"date":"datetime-local"} value={utcInput(p.ends_at??"",p.precision)} onChange={e=>patch(i,{ends_at:e.target.value?serializeTime(e.target.value,p.precision):null})}/></label>
        <label>Confidence<select value={p.confidence} onChange={e=>patch(i,{confidence:e.target.value as ScheduleFields["confidence"]})}><option value="estimated">Estimated</option><option value="confirmed">Confirmed</option></select></label>
      </fieldset>)}
      <label className="calendar-checkbox"><input type="checkbox" disabled={busy} checked={review===fingerprint} onChange={e=>setReview(e.target.checked?fingerprint:"")}/>I reviewed all phases and their local dates</label>
    </div>}
    {error&&<p role="alert">{error}</p>}
    <div className="calendar-controls"><button type="button" className="button button--primary" disabled={busy||!phases.length||review!==fingerprint||phases.some(p=>!p.starts_at)} onClick={()=>void save()}>Save cycle</button><button type="button" className="button button--quiet" disabled={busy} onClick={()=>{if(allowNavigation())onClose();}}>Close cycle editor</button></div>
  </section>;
}
export function CycleDetails({groupId,cycleId,onSelect}:{groupId:string;cycleId:string;onSelect:(row:CalendarOccurrence)=>void}){
  const [items,setItems]=useState<CalendarOccurrence[]|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    api.calendarCycle(groupId,cycleId,controller.signal).then(r=>{if(!controller.signal.aborted)setItems(r.items);}).catch(()=>{if(!controller.signal.aborted)setError("Unable to load linked phases");});
    return ()=>controller.abort();
  },[groupId,cycleId]);
  return <section className="calendar-stage-timeline" aria-label="Linked event cycle"><h3>Linked event cycle</h3>{error?<p role="alert">{error}</p>:!items?<p>Loading phases…</p>:<div className="calendar-stage-tabs">{items.map(p=><button type="button" key={p.id} className="button button--quiet" onClick={()=>onSelect(p)}>{p.phase} · {p.starts_at} · {p.schedule_status==="cancelled"?"Cancelled":p.confidence}</button>)}</div>}</section>;
}
