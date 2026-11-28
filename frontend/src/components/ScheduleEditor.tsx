import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type StateCalendarProfile } from "../lib/api";
import { eventTypeOptions, eventLabel } from "../lib/format";
import type { Alliance } from "../lib/types";
import type { CalendarOccurrence } from "../lib/calendar";
import { gameEventForCalendar, repeatLabel } from "../lib/game-event-catalog";
import { fixedGameInterval, forecastRows, intervalPayload, sourceRunWarning, stateAge } from "../lib/game-forecast";
import { futureChange, scheduleFields, serializeTime, utcInput, type ScheduleFields } from "../lib/schedule-editor";

type Props={groupId:string;alliances:Alliance[];preferred?:string;day:string;row:CalendarOccurrence|null;onClose:()=>void;onSaved:(day:string)=>void};
const message=(e:unknown)=>e instanceof Error?e.message:"Unable to save schedule";
export function ScheduleEditor({groupId,alliances,preferred,day,row,onClose,onSaved}:Props){
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const defaultAlliance=active.find(a=>a.id===preferred)??active[0];
  const [fields,setFields]=useState<ScheduleFields>(()=>row?scheduleFields(row):{event_type:"bear_trap",scope:"alliance",alliance_id:defaultAlliance?.id??null,state_id:defaultAlliance?.state_id??"",starts_at:day,ends_at:null,precision:"date",phase:"",confidence:"confirmed"});
  const [count,setCount]=useState(1);
  const [days,setDays]=useState(2);
  const [intervalUnit,setIntervalUnit]=useState<"days"|"hours"|"minutes">("days");
  const [profiles,setProfiles]=useState<StateCalendarProfile[]>([]);
  const [manualDate,setManualDate]=useState<{stateId:string;value:string}|null>(null);
  const [profileError,setProfileError]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    api.stateCalendarProfiles(groupId,controller.signal).then(r=>{if(!controller.signal.aborted)setProfiles(r.items);}).catch(()=>{if(!controller.signal.aborted)setProfileError("State reference unavailable; enter a date manually.");});
    return ()=>controller.abort();
  },[groupId]);
  const profile=profiles.find(p=>p.state_id===fields.state_id);
  const stateStart=manualDate?.stateId===fields.state_id?manualDate.value:profile?.opened_on??"";
  async function saveStateDate(clear:boolean){
    if(!profile||busy||lock.current)return;
    lock.current=true;setBusy(true);setProfileError("");
    try{
      const updated=await api.updateStateCalendarProfile(groupId,fields.state_id,clear?null:stateStart,profile.revision);
      setProfiles(old=>old.map(p=>p.state_id===updated.state_id?updated:p));
      setManualDate(null);
    }catch(e){setProfileError(message(e));}finally{lock.current=false;setBusy(false);}
  }
  const [reviewed,setReviewed]=useState<string|null>(null);
  const [status,setStatus]=useState(row?.schedule_status??"scheduled");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const request=useRef<{fingerprint:string;key:string}|null>(null);
  const lock=useRef(false);
  const states=[...new Set(active.map(a=>a.state_id))];
  const patch=(next:Partial<ScheduleFields>)=>setFields(old=>({...old,...next}));
  const changeOwner=(value:string)=>{
    const a=active.find(a=>a.id===value);
    if(a)patch({scope:"alliance",alliance_id:a.id,state_id:a.state_id});
    else patch({scope:"state",alliance_id:null,state_id:value.slice(6)});
  };
  const changePrecision=(precision:ScheduleFields["precision"])=>setFields(old=>({...old,precision,starts_at:precision==="date"?old.starts_at.slice(0,10):old.starts_at.slice(0,10)+"T00:00Z",ends_at:null}));
  const reference=gameEventForCalendar(fields.event_type);
  const suggested=fixedGameInterval(reference);
  const minutes=days*({days:1440,hours:60,minutes:1}[intervalUnit]);
  const warnings=sourceRunWarning(reference,fields.event_type,fields);
  let preview:ReturnType<typeof forecastRows>=[],previewError="",age:number|null=null;
  if(!row){
    try{
      preview=forecastRows(fields,count,minutes);
      if(stateStart)age=stateAge(stateStart,fields.starts_at);
      if(age!==null&&reference?.unlockDay!==undefined&&age<reference.unlockDay)warnings.push("Anchor is earlier than the reference unlock day "+reference.unlockDay+". Verify availability in game.");
    }catch(e){previewError=message(e);}
  }
  const fingerprint=JSON.stringify({fields,count,minutes,stateStart});
  function useReference(){
    if(suggested===null)return;
    const unit=suggested%1440===0?"days":suggested%60===0?"hours":"minutes";
    setIntervalUnit(unit);setDays(suggested/({days:1440,hours:60,minutes:1}[unit]));setCount(4);setReviewed(null);
  }
  async function save(e:FormEvent){
    e.preventDefault();if(lock.current)return;
    lock.current=true;setBusy(true);setError("");
    try{
      if(!fields.state_id||!fields.starts_at)throw new Error("Choose a scope and start date");
      if(fields.ends_at&&fields.ends_at<=fields.starts_at)throw new Error("End must follow start");
      if(row){
        const result=await api.updateSchedule(groupId,row.id,{...fields,revision:row.revision,schedule_status:status});
        onSaved(result.starts_at.slice(0,10));
      }else{
        if(previewError)throw Error(previewError);
        if(count>1&&reviewed!==fingerprint)throw Error("Review and confirm the proposed dates first");
        const payload={...fields,...intervalPayload(count,minutes,fields.precision),...(count>1?{reject_existing:true}:{})};
        const requestFingerprint=JSON.stringify(payload);
        if(request.current?.fingerprint!==requestFingerprint)request.current={fingerprint:requestFingerprint,key:crypto.randomUUID()};
        const result=await api.createSchedule(groupId,{...payload,request_key:request.current.key});
        onSaved(result.items[0].starts_at.slice(0,10));
      }
    }catch(e){setError(message(e));}finally{lock.current=false;setBusy(false);}
  }
  const timeType=fields.precision==="date"?"date":"datetime-local";
  return <section className="data-panel calendar-editor" aria-label="Schedule editor">
    <h2>{row?"Edit scheduled event":"Add scheduled event"}</h2>
    <p>Planning only. No attendance or result records are created.</p>
    <form onSubmit={save}>
      <fieldset disabled={busy} className="calendar-editor-fields">
        <label>Event type<select value={fields.event_type} onChange={e=>patch({event_type:e.target.value})}>{eventTypeOptions.map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
        <label>Schedule owner<select required value={fields.scope==="alliance"?fields.alliance_id??"":"state:"+fields.state_id} onChange={e=>changeOwner(e.target.value)}><option value="" disabled>Choose owner</option>{active.map(a=><option key={a.id} value={a.id}>{a.tag} · #{a.state_id}</option>)}{states.map(s=><option key={s} value={"state:"+s}>State #{s}</option>)}</select></label>
        <label>Precision<select value={fields.precision} onChange={e=>changePrecision(e.target.value as ScheduleFields["precision"])}><option value="date">Date only (time not set)</option><option value="minute">Date and UTC time</option></select></label>
        <label>Starts (UTC)<input required type={timeType} value={utcInput(fields.starts_at,fields.precision)} onChange={e=>patch({starts_at:e.target.value?serializeTime(e.target.value,fields.precision):""})}/></label>
        <label>Ends (UTC, optional, exclusive)<input type={timeType} value={utcInput(fields.ends_at??"",fields.precision)} onChange={e=>patch({ends_at:e.target.value?serializeTime(e.target.value,fields.precision):null})}/></label>
        <label>Phase (optional)<input maxLength={80} value={fields.phase} onChange={e=>patch({phase:e.target.value})}/></label>
        <label>Confidence<select value={fields.confidence} onChange={e=>patch({confidence:e.target.value as ScheduleFields["confidence"]})}><option value="confirmed">Confirmed</option><option value="estimated">Estimated</option></select></label>
        {row?<label>Schedule status<select value={status} onChange={e=>setStatus(e.target.value as CalendarOccurrence["schedule_status"])}><option value="scheduled">Scheduled</option><option value="cancelled">Cancelled</option></select></label>:<>
        <label>Occurrences (including first)<input type="number" min={1} max={180} required value={count} onChange={e=>setCount(Number(e.target.value))}/></label>
        {count>1&&<><label>Repeat every ({intervalUnit})<input type="number" min={1} step={intervalUnit==="hours"?"any":1} required value={days} onChange={e=>setDays(Number(e.target.value))}/></label><label>Repeat unit<select value={intervalUnit} onChange={e=>setIntervalUnit(e.target.value as typeof intervalUnit)}><option value="days">Days</option><option value="hours">Hours</option><option value="minutes">Minutes</option></select></label></>}
        <label>State start date (optional, reference only)<input type="date" value={stateStart} onChange={e=>setManualDate({stateId:fields.state_id,value:e.target.value})}/></label>
        </>}
      </fieldset>
      {!row&&<>
        <p>State #{fields.state_id} · {profile?.source==="whiteoutstats"?"WhiteoutStats":profile?.source==="manual"?"Saved manual date":"Opening date unavailable"}{profile?.age_days!=null?" · "+profile.age_days+" days old":""}{profile?.last_success_at?" · Last received "+profile.last_success_at:""}{profile?.last_status==="failed"?" · Provider refresh failed; cached date retained":""}</p>
        {profile&&<div className="calendar-controls"><button type="button" className="button button--quiet" disabled={busy||!stateStart} onClick={()=>void saveStateDate(false)}>Save state date override</button>{profile.manual_opened_on&&<button type="button" className="button button--quiet" disabled={busy} onClick={()=>void saveStateDate(true)}>Use provider date</button>}</div>}
        {profileError&&<p role="alert">{profileError}</p>}
        {reference&&<div className="game-catalog-summary"><strong>Game reference</strong><p>{repeatLabel(reference.schedule?.repeat)} · {reference.duration??"Duration unavailable"}</p>{reference.unlockDay!==undefined&&<p>Reference unlock: state day {reference.unlockDay}{age!==null?" · Anchor age: "+age+" days":""}</p>}
          {suggested!==null&&<button type="button" className="button button--quiet" disabled={busy} onClick={useReference}>Use game repeat rule</button>}
          {warnings.map(w=><p key={w}>{w}</p>)}
          <small>Verify the anchor, local rotation and end time. Game reference does not confirm actual dates.</small></div>}
        {count>1&&<div className="calendar-series-preview"><h3>Proposed schedule</h3><p>Future occurrences are estimated. Maximum horizon: 366 days.</p>
          {previewError?<p role="alert">{previewError}</p>:<ul>{preview.map(r=><li key={r.start}>{r.start}{r.end?" — "+r.end:""} · {r.confidence}</li>)}</ul>}
          <label className="calendar-checkbox"><input type="checkbox" disabled={busy||!!previewError} checked={reviewed===fingerprint} onChange={e=>setReviewed(e.target.checked?fingerprint:null)}/>I reviewed these dates and confirmed the local repeat pattern</label>
        </div>}
      </>}
      {error&&<p role="alert">{error}</p>}
      <div className="calendar-controls"><button className="button button--primary" disabled={busy||!active.length||(!row&&count>1&&(!!previewError||reviewed!==fingerprint))} type="submit">{busy?"Saving…":"Save schedule"}</button><button type="button" className="button button--quiet" disabled={busy} onClick={onClose}>Close editor</button></div>
    </form>
  </section>;
}
export function FutureScheduleEditor({groupId,row,onClose,onSaved}:{groupId:string;row:CalendarOccurrence;onClose:()=>void;onSaved:()=>void}){
  const [preview,setPreview]=useState<CalendarOccurrence[]|null>(null);
  const [action,setAction]=useState<"shift"|"cancel">("shift");
  const [minutes,setMinutes]=useState(row.precision==="date"?1440:60);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const lock=useRef(false);
  async function run(save:boolean){
    if(lock.current)return;lock.current=true;setBusy(true);setError("");
    try{
      if(save&&preview){await api.changeScheduleFuture(groupId,row.id,futureChange(preview,action,minutes));onSaved();}
      else setPreview((await api.previewScheduleFuture(groupId,row.id)).items);
    }catch(e){setError(message(e));setPreview(null);}finally{lock.current=false;setBusy(false);}
  }
  return <section className="data-panel calendar-editor" aria-label="Future series editor">
    <h2>Change this and future occurrences</h2>
    <p>Past occurrences, cancelled entries and other manual overrides are preserved.</p>
    <fieldset className="calendar-editor-fields" disabled={busy}>
      <label>Series action<select value={action} onChange={e=>{setAction(e.target.value as "shift"|"cancel");setPreview(null);}}><option value="shift">Shift schedule</option><option value="cancel">Cancel occurrences</option></select></label>
      {action==="shift"&&<label>Shift (signed minutes)<input type="number" step={row.precision==="date"?1440:1} value={minutes} onChange={e=>{setMinutes(Number(e.target.value));setPreview(null);}}/></label>}
    </fieldset>
    {preview&&<div className="calendar-series-preview"><h3>{preview.length} affected occurrences</h3><ul>{preview.map(r=><li key={r.id}>{eventLabel(r.event_type)} · {r.starts_at}{action==="shift"&&Number.isFinite(minutes)&&" → "+new Date(Date.parse(r.precision==="date"?r.starts_at+"T00:00Z":r.starts_at)+minutes*60000).toISOString().slice(0,r.precision==="date"?10:16)+(r.precision==="minute"?"Z":"")}</li>)}</ul></div>}
    {error&&<p role="alert">{error}</p>}
    <div className="calendar-controls"><button className="button button--quiet" disabled={busy} onClick={()=>void run(false)}>Preview affected occurrences</button><button className="button button--primary" disabled={busy||!preview?.length} onClick={()=>void run(true)}>Apply series change</button><button className="button button--quiet" disabled={busy} onClick={onClose}>Close editor</button></div>
  </section>;
}
