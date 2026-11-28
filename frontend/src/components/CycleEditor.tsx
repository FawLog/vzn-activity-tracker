import { allowNavigation, useNavigationGuard } from "../lib/navigation-guard";
import {useEffect,useRef,useState} from "react";
import {api} from "../lib/api";
import {cycleDraft,cycleIntervalDays,cycleOccurrences,moveCyclePhaseStart,legionPhases,cycleReference,initialCycleCount,type CycleKind,type CycleSeries} from "../lib/calendar-cycles";
import {creationEventOptions,cycleTypes} from "../lib/calendar-event-options";
import {weekStart,type CalendarOccurrence} from "../lib/calendar";
import {serializeTime,utcInput,type ScheduleFields} from "../lib/schedule-editor";
import type {Alliance} from "../lib/types";
import {CycleReconcileEditor} from "./CycleReconcileEditor";
type Props={onAdvanced?:(type:string)=>void;onEvent?:(type:string)=>void;initialKind?:CycleKind;groupId:string;alliances:Alliance[];preferred?:string;day:string;onClose:()=>void;onSaved:(day:string)=>void};
export function CycleEditor({initialKind="canyon",onAdvanced,onEvent,groupId,alliances,preferred,day,onClose,onSaved}:Props){
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const [kind,setKind]=useState<CycleKind>(initialKind);
  const [owner,setOwner]=useState(active.find(a=>a.id===preferred)?.id??active[0]?.id??"");
  const [anchor,setAnchor]=useState(weekStart(day));
  const [phases,setPhases]=useState<ScheduleFields[]>([]);
  const [count,setCount]=useState(3);
  const [rolling,setRolling]=useState(true);
  const [twoLegions,setTwoLegions]=useState(false);
  const interval=cycleIntervalDays(kind);
  const canRoll=interval!==null&&interval>=7&&interval<=60;
  const autoRenew=rolling&&canRoll;
  const effectiveCount=initialCycleCount(interval,autoRenew,count);
  let cycles:ScheduleFields[][]=[],repeatError="";
  if(phases.length)try{cycles=cycleOccurrences(kind,phases,effectiveCount,interval??1);}catch(e){repeatError=e instanceof Error?e.message:"Invalid cycle";}
  const [review,setReview]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  const request=useRef<{fingerprint:string;key:string}|null>(null);
  const fingerprint=JSON.stringify({kind,owner,anchor,phases,effectiveCount,twoLegions,autoRenew});
  const initial=useRef(fingerprint);
  useNavigationGuard(initial.current!==fingerprint,busy);
  const invalidate=()=>{setPhases([]);setReview("");setError("");};
  function preview(){
    try{
      const a=active.find(a=>a.id===owner);
      if(!a)throw Error("Choose an active alliance");
      const draft=cycleDraft(kind,anchor,a.state_id,a.id);
      setPhases(kind==="svs"?draft:legionPhases(draft,twoLegions));setReview("");setError("");
    }catch(e){setError(e instanceof Error?e.message:"Unable to preview");}
  }
  function patch(index:number,next:Partial<ScheduleFields>){
    setPhases(old=>old.map((p,i)=>i===index?{...p,...next}:p));setReview("");
  }
  async function save(){
    if(lock.current||review!==fingerprint||!phases.length||repeatError||effectiveCount>1&&interval===null)return;
    lock.current=true;setBusy(true);setError("");
    try{
      if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
      const result=await api.createCycle(groupId,{kind,phases,request_key:request.current.key,...(effectiveCount>1&&interval!==null?{occurrence_count:effectiveCount,interval_days:interval,rolling:autoRenew}:{})});
      onSaved(result.items[0].starts_at.slice(0,10));
    }catch(e){setError(e instanceof Error?e.message:"Unable to save cycle");}
    finally{lock.current=false;setBusy(false);}
  }
  return <section className="data-panel calendar-editor" aria-label="Cycle editor">
    <h2>Add event cycle</h2><p>Review every phase. This creates linked calendar entries only, never actual event results.</p>
    <fieldset disabled={busy} className="calendar-editor-fields">
      <label>Event type<select value={"cycle:"+kind} onChange={e=>{const type=e.target.value;if(onEvent){onEvent(type);return;}if(cycleTypes[type]){setKind(cycleTypes[type]);invalidate();}}}>{creationEventOptions.filter(([type])=>onEvent||cycleTypes[type]).map(([type,label])=><option key={type} value={type}>{label}</option>)}</select></label>
      <label>{kind==="svs"?"State (via active alliance)":"Alliance"}<select value={owner} onChange={e=>{setOwner(e.target.value);invalidate();}}>{active.map(a=><option key={a.id} value={a.id}>{a.tag} · #{a.state_id}</option>)}</select></label>
      <label>Event starts (Monday, 00:00 UTC)<input type="date" value={anchor} onChange={e=>{setAnchor(e.target.value);invalidate();}}/></label>
      {canRoll&&<label className="calendar-checkbox"><input type="checkbox" checked={autoRenew} onChange={e=>{setRolling(e.target.checked);setReview("");}}/>Automatically maintain full cycles</label>}
      {!autoRenew&&<label>Cycles to schedule (including first)<input type="number" min={1} max={interval?Math.min(14,1+Math.floor(366/interval)):1} value={count} onChange={e=>{setCount(Number(e.target.value));setReview("");}}/></label>}
      <small>{interval?"Game repeat rule: every "+interval+" days. Future cycles are estimates. "+(autoRenew?"Initial 60-day preview; renewed automatically.":"Finite preview.")+"":"No fixed repeat rule; schedule one cycle."}</small>
      {kind!=="svs"&&<label className="calendar-checkbox"><input type="checkbox" checked={twoLegions} onChange={e=>{setTwoLegions(e.target.checked);if(phases.length)setPhases(legionPhases(phases,e.target.checked));setReview("");}}/>Schedule Legion 2</label>}
      <button type="button" className="button button--quiet" onClick={preview}>Preview cycle</button>
      {kind!=="svs"&&onAdvanced&&<button type="button" className="button button--quiet" onClick={()=>{if(allowNavigation())onAdvanced(kind);}}>Advanced: schedule battle only</button>}
    </fieldset>
    {!!phases.length&&<div className="calendar-series-preview calendar-cycle-preview">
      <p>All suggested dates are estimated. {kind==="svs"?"Review the extended preparation day.":"Set confirmed legion times when known."}</p>
      {cycleReference(kind)?.scheduleOverride&&<p><a href={cycleReference(kind)?.scheduleOverride?.source} target="_blank" rel="noreferrer">Official schedule supplement</a> · {cycleReference(kind)?.scheduleOverride?.note}</p>}
      {phases.map((p,i)=><fieldset key={p.phase} disabled={busy} className="calendar-editor-fields"><legend>{p.phase}</legend>
        <label>Precision<select value={p.precision} onChange={e=>{const precision=e.target.value as ScheduleFields["precision"];patch(i,moveCyclePhaseStart({...p,precision,starts_at:"",ends_at:null},precision==="date"?p.starts_at.slice(0,10):""));}}><option value="date">Date only</option><option value="minute">UTC time</option></select></label>
        <label>Starts (UTC)<input type={p.precision==="date"?"date":"datetime-local"} value={utcInput(p.starts_at,p.precision)} onChange={e=>{const starts_at=e.target.value?serializeTime(e.target.value,p.precision):"";patch(i,moveCyclePhaseStart(p,starts_at));}}/></label>
        <label>Ends (optional, exclusive)<input type={p.precision==="date"?"date":"datetime-local"} value={utcInput(p.ends_at??"",p.precision)} onChange={e=>patch(i,{ends_at:e.target.value?serializeTime(e.target.value,p.precision):null})}/></label>
        <label>Confidence<select value={p.confidence} onChange={e=>patch(i,{confidence:e.target.value as ScheduleFields["confidence"]})}><option value="estimated">Estimated</option><option value="confirmed">Confirmed</option></select></label>
      </fieldset>)}
      {repeatError?<p role="alert">{repeatError}</p>:cycles.length>1&&<div><h3>Future cycles</h3><p>Future legion battle times remain unconfirmed. Verify each local cycle.</p><ul>{cycles.slice(1).map((rows,i)=><li key={i}>{rows[0].starts_at} — {rows[rows.length-1].starts_at} · Estimated</li>)}</ul></div>}
      <label className="calendar-checkbox"><input type="checkbox" disabled={busy||!!repeatError} checked={review===fingerprint} onChange={e=>setReview(e.target.checked?fingerprint:"")}/>I reviewed all phases and their local dates</label>
    </div>}
    {error&&<p role="alert">{error}</p>}
    <div className="calendar-controls"><button type="button" className="button button--primary" disabled={busy||!phases.length||review!==fingerprint||!!repeatError||effectiveCount>1&&interval===null||phases.some(p=>!p.starts_at)} onClick={()=>void save()}>Save cycle</button><button type="button" className="button button--quiet" disabled={busy} onClick={()=>{if(allowNavigation())onClose();}}>Close cycle editor</button></div>
  </section>;
}
export function CycleDetails({groupId,cycleId,onSelect,writable,onChanged}:{groupId:string;cycleId:string;onSelect:(row:CalendarOccurrence)=>void;writable:boolean;onChanged:(day?:string)=>void}){
  const [items,setItems]=useState<CalendarOccurrence[]|null>(null);
  const [series,setSeries]=useState<CycleSeries|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    api.calendarCycle(groupId,cycleId,controller.signal).then(r=>{if(!controller.signal.aborted){setItems(r.items);setSeries(r.series);}}).catch(()=>{if(!controller.signal.aborted)setError("Unable to load linked phases");});
    return ()=>controller.abort();
  },[groupId,cycleId]);
  return <section className="calendar-stage-timeline" aria-label="Linked event cycle"><h3>Linked event cycle</h3>{error?<p role="alert">{error}</p>:!items?<p>Loading phases…</p>:<div className="calendar-stage-tabs">{items.map(p=><button type="button" key={p.id} className="button button--quiet" onClick={()=>onSelect(p)}>{p.phase} · {p.starts_at} · {p.schedule_status==="cancelled"?"Cancelled":p.confidence}</button>)}</div>}{series&&<p>Cycle schedule: {series.status} · Every {series.interval_days} days</p>}{items&&writable&&<CycleReconcileEditor groupId={groupId} cycleId={cycleId} series={series} onChanged={onChanged}/>}</section>;
}
