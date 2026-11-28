import { allowNavigation, useNavigationGuard } from "../lib/navigation-guard";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type StateCalendarProfile } from "../lib/api";
import { eventTypeOptions, eventLabel } from "../lib/format";
import type { Alliance } from "../lib/types";
import type { CalendarOccurrence } from "../lib/calendar";
import { gameEventForCalendar, eventRepeatLabel, followType } from "../lib/game-event-catalog";
import { FollowScheduleEditor } from "./FollowScheduleEditor";
import { fixedGameInterval, forecastRows, advancedPlan, sourceRunWarning, referenceDuration, referenceEnd, referenceRepeat, stateAge, type RepeatMode } from "../lib/game-forecast";
import { futureChange, precisionChange, scheduleFields, serializeTime, utcInput, templateFields, bearCycleDates, moveScheduleStart, futureEditDates, type FuturePreview, type ScheduleTemplate, type ScheduleFields } from "../lib/schedule-editor";

import type { RotationForecast } from "../lib/state-rotation";
import { BearScheduleEditor } from "./BearScheduleEditor";
import {creationEventOptions,creationType,cycleTypes} from "../lib/calendar-event-options";
import type {CycleKind} from "../lib/calendar-cycles";
type Props={manualType?:string;forecast?:RotationForecast;groupId:string;alliances:Alliance[];preferred?:string;day:string;row:CalendarOccurrence|null;onCycle?:(kind:CycleKind)=>void;onClose:()=>void;onSaved:(day:string)=>void};
const message=(e:unknown)=>e instanceof Error?e.message:"Unable to save schedule";
export function ScheduleEditor(props:Props){
  const [type,setType]=useState(props.manualType??"bear:batch");
  const [independent,setIndependent]=useState(false);
  function choose(value:string){if(!allowNavigation())return;if(cycleTypes[value]){props.onCycle?.(cycleTypes[value]);return;}setType(value);setIndependent(false);}
  if(!props.row&&!props.forecast&&followType(type)&&!independent)return <FollowScheduleEditor key={type} eventType={type} groupId={props.groupId} alliances={props.alliances} preferred={props.preferred} day={props.day} onEvent={choose} onManual={()=>{if(allowNavigation())setIndependent(true);}} onClose={props.onClose} onSaved={props.onSaved}/>;
  if(!props.row&&!props.forecast&&type==="bear:batch")return <BearScheduleEditor groupId={props.groupId} alliances={props.alliances} preferred={props.preferred} day={props.day} onClose={props.onClose} onSaved={props.onSaved} onEvent={value=>{
    if(cycleTypes[value]){props.onCycle?.(cycleTypes[value]);return;}
    if(allowNavigation()){setType(value);setIndependent(false);}
  }}/>;
  return <GeneralScheduleEditor key={type} {...props} initialType={type==="bear:batch"?"bear_trap":type} onBear={()=>choose("bear:batch")} onFollow={choose}/>;
}
function GeneralScheduleEditor({forecast,groupId,alliances,preferred,day,row,onCycle,onClose,onSaved,initialType,onBear,onFollow}:Props&{initialType:string;onBear:()=>void;onFollow:(type:string)=>void}){
  const initialRepeat=referenceRepeat(gameEventForCalendar(initialType));
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const defaultAlliance=active.find(a=>a.id===preferred)??active[0];
  const [autoEnd,setAutoEnd]=useState(!row&&!forecast);
  const [fields,setFields]=useState<ScheduleFields>(()=>{
    if(row)return scheduleFields(row);
    if(forecast)return {...forecast.fields};
    const next:ScheduleFields={event_type:initialType,scope:followType(initialType)?"state":"alliance",alliance_id:followType(initialType)?null:defaultAlliance?.id??null,state_id:defaultAlliance?.state_id??"",starts_at:day,ends_at:null,precision:"date",phase:"",confidence:"confirmed"};
    return {...next,ends_at:referenceEnd(gameEventForCalendar(initialType),next)};
  });
  const [count,setCount]=useState(forecast?.count??(row?1:initialRepeat.count));
  const [renew,setRenew]=useState(!forecast);
  const [groupBear,setGroupBear]=useState(false);
  const [bearAnchor,setBearAnchor]=useState("");
  const [bearKey,setBearKey]=useState("");
  const [advanced,setAdvanced]=useState(!!row);
  const [repeatMode,setRepeatMode]=useState<RepeatMode>(row||forecast?"fixed":initialRepeat.mode);
  const [months,setMonths]=useState(initialRepeat.months);
  const [weekdays,setWeekdays]=useState<number[]>(initialRepeat.weekdays.length?initialRepeat.weekdays:[1,3]);
  const [days,setDays]=useState(forecast?forecast.interval/1440:initialRepeat.days);
  const [intervalUnit,setIntervalUnit]=useState<"days"|"hours"|"minutes">("days");
  const [profiles,setProfiles]=useState<StateCalendarProfile[]>([]);
  const [templates,setTemplates]=useState<ScheduleTemplate[]>([]);
  const [templateName,setTemplateName]=useState("");
  const [templateError,setTemplateError]=useState("");
  const [templateMessage,setTemplateMessage]=useState("");
  useEffect(()=>{
    if(row)return;
    const controller=new AbortController();
    api.scheduleTemplates(groupId,controller.signal).then(r=>{if(!controller.signal.aborted)setTemplates(r.items);}).catch(()=>{if(!controller.signal.aborted)setTemplateError("Saved templates unavailable.");});
    return ()=>controller.abort();
  },[groupId,row]);
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
  const [decision,setDecision]=useState<FuturePreview|null>(null);
  const [editScope,setEditScope]=useState<"single"|"future">("single");
  const [editHours,setEditHours]=useState(48);
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
  const changePrecision=(precision:ScheduleFields["precision"])=>setFields(old=>{const next=precisionChange(old,precision);return autoEnd?{...next,ends_at:referenceEnd(gameEventForCalendar(next.event_type),next)}:next;});
  const reference=gameEventForCalendar(fields.event_type);
  const suggested=fixedGameInterval(reference);
  const referencePlan=referenceRepeat(reference,true);
  const minutes=days*({days:1440,hours:60,minutes:1}[intervalUnit]);
  const rolling=!row&&renew&&count>1&&count<=60&&repeatMode==="fixed"&&minutes>=1440;
  const grouping=!row&&groupBear&&fields.event_type==="bear_trap"&&fields.scope==="alliance";
  const warnings=sourceRunWarning(reference,fields.event_type,fields);
  let preview:ReturnType<typeof forecastRows>=[],previewError="",age:number|null=null,cycleDates:string[]=[];
  if(!row){
    try{
      preview=advancedPlan(fields,count,minutes,repeatMode,months,weekdays).rows;
      if(grouping)cycleDates=bearCycleDates(fields,bearAnchor,bearKey,count,minutes,repeatMode);
      if(stateStart)age=stateAge(stateStart,fields.starts_at);
      if(age!==null&&reference?.unlockDay!==undefined&&age<reference.unlockDay)warnings.push("Anchor is earlier than the reference unlock day "+reference.unlockDay+". Verify availability in game.");
    }catch(e){previewError=message(e);}
  }
  const fingerprint=JSON.stringify({fields,count,minutes,stateStart,repeatMode,months,weekdays,renew,groupBear,bearAnchor,bearKey});
  const initial=useRef(JSON.stringify({fields,count,minutes,repeatMode,months,weekdays,status,renew,groupBear,bearAnchor,bearKey}));
  useNavigationGuard(initial.current!==JSON.stringify({fields,count,minutes,repeatMode,months,weekdays,status,renew,groupBear,bearAnchor,bearKey})||manualDate!==null||!!templateName.trim()||decision!==null,busy);
  function useReference(){
    if(suggested!==null){
      const unit=suggested%1440===0?"days":suggested%60===0?"hours":"minutes";
      setRepeatMode("fixed");setIntervalUnit(unit);setDays(suggested/({days:1440,hours:60,minutes:1}[unit]));setCount(Math.min(4,1+Math.floor(366*1440/suggested)));setReviewed(null);
    }else if(referencePlan.count>1){
      setRepeatMode(referencePlan.mode);setMonths(referencePlan.months);setWeekdays(referencePlan.weekdays);setCount(referencePlan.count);setReviewed(null);
    }
  }
  function changeEvent(type:string){
    if(!row&&type==="bear:batch"){onBear();return;}
    if(!row&&cycleTypes[type]){onCycle?.(cycleTypes[type]);return;}
    if(!row&&followType(type)){onFollow(type);return;}
    setReviewed(null);setGroupBear(false);setBearAnchor("");setBearKey("");
    if(row){patch({event_type:type});return;}
    setAutoEnd(true);
    setFields(old=>{const next={...old,event_type:type,phase:"",ends_at:null};return {...next,ends_at:referenceEnd(gameEventForCalendar(type),next)};});
    const plan=referenceRepeat(gameEventForCalendar(type));
    setRepeatMode(plan.mode);setIntervalUnit("days");setDays(plan.days);setMonths(plan.months);setWeekdays(plan.weekdays.length?plan.weekdays:[1,3]);setCount(plan.count);
  }
  const localTemplates=templates.filter(t=>t.alliance_id===fields.alliance_id&&fields.scope==="alliance");
  function applyTemplate(id:string){
    const template=localTemplates.find(t=>t.id===id);
    if(!template||!allowNavigation())return;
    try{
      const data=template.schedule;
      const next=templateFields(data,fields.starts_at.slice(0,10)||day);
      setAutoEnd(false);setFields(next);setCount(data.occurrence_count);setRenew(!!data.rolling);setGroupBear(false);setBearAnchor("");setBearKey("");
      setRepeatMode(data.repeat_months?"months":data.repeat_weekdays?.length?"weekdays":"fixed");
      setMonths(data.repeat_months??1);setWeekdays(data.repeat_weekdays??[1,3]);
      const interval=data.interval_minutes??2880,unit=interval%1440===0?"days":interval%60===0?"hours":"minutes";
      setIntervalUnit(unit);setDays(interval/({days:1440,hours:60,minutes:1}[unit]));
      setTemplateName("");setManualDate(null);setReviewed(null);setTemplateError("");setTemplateMessage("Template loaded. Verify the next date and local times before saving.");
    }catch(e){setTemplateError(message(e));}
  }
  async function saveTemplate(){
    if(lock.current||!templateName.trim()||fields.scope!=="alliance"||previewError)return;
    lock.current=true;setBusy(true);setTemplateError("");setTemplateMessage("");
    try{
      const schedule={...fields,...advancedPlan(fields,count,minutes,repeatMode,months,weekdays).payload,reject_existing:true,rolling};
      const saved=await api.saveScheduleTemplate(groupId,templateName.trim(),schedule);
      setTemplates(old=>[...old,saved]);setTemplateName("");setTemplateMessage("Template saved. No calendar entries were created.");
    }catch(e){setTemplateError(message(e));}finally{lock.current=false;setBusy(false);}
  }
  async function deleteTemplate(template:ScheduleTemplate){
    if(lock.current||!window.confirm("Delete saved template "+template.name+"? Scheduled events will not change."))return;
    lock.current=true;setBusy(true);setTemplateError("");setTemplateMessage("");
    try{await api.deleteScheduleTemplate(groupId,template.id);setTemplates(old=>old.filter(t=>t.id!==template.id));setTemplateMessage("Template deleted.");}
    catch(e){setTemplateError(message(e));}finally{lock.current=false;setBusy(false);}
  }
  const eligibleSeries=!!row?.series_id&&row.schedule_status==="scheduled"&&row.starts_at>=(row.precision==="date"?new Date().toISOString().slice(0,10):new Date().toISOString().slice(0,16)+"Z")&&
    (["event_type","scope","alliance_id","state_id","phase","precision"] as const).every(k=>fields[k]===row[k]);
  let editedDates:ReturnType<typeof futureEditDates>=[],editError="";
  if(decision&&editScope==="future"&&status==="scheduled"){
    try{editedDates=futureEditDates(decision,fields,editHours);}catch(e){editError=message(e);}
  }
  async function save(e:FormEvent){
    e.preventDefault();if(lock.current)return;
    lock.current=true;setBusy(true);setError("");
    try{
      if(!fields.state_id||!fields.starts_at)throw new Error("Choose a scope and start date");
      if(fields.ends_at&&fields.ends_at<=fields.starts_at)throw new Error("End must follow start");
      if(row){
        const schedule={...fields,revision:row.revision,schedule_status:status};
        if(eligibleSeries&&!decision){
          const result=await api.previewScheduleFuture(groupId,row.id);
          if(result.items[0]?.id!==row.id||result.items[0]?.revision!==row.revision)throw Error("Schedule changed; reopen the event before editing.");
          setDecision(result);setEditScope("single");setEditHours((result.interval_minutes??2880)/60);
          return;
        }
        if(decision&&editScope==="future"){
          if(status==="cancelled"){
            await api.changeScheduleFuture(groupId,row.id,futureChange(decision.items,"cancel",0));
          }else{
            if(editError)throw Error(editError);
            await api.changeScheduleFuture(groupId,row.id,{action:"edit",schedule,
              ...(decision.interval_minutes!==null?{interval_minutes:Math.round(editHours*60)}:{}),
              revisions:Object.fromEntries(decision.items.map(r=>[r.id,r.revision]))});
          }
          onSaved((status==="cancelled"?row.starts_at:fields.starts_at).slice(0,10));
        }else{
          const result=await api.updateSchedule(groupId,row.id,schedule);
          onSaved(result.starts_at.slice(0,10));
        }
      }else{
        if(previewError)throw Error(previewError);
        if(reference?.id==="hall-of-chief"&&!["Season 1","Season 2"].includes(fields.phase))throw Error("Choose the event season");
        if(reference?.id==="frostfire-mine"&&fields.precision!=="minute")throw Error("Choose the actual game time slot");
        if(count>1&&reviewed!==fingerprint)throw Error("Review and confirm the proposed dates first");
        const payload={...fields,...advancedPlan(fields,count,minutes,repeatMode,months,weekdays).payload,...(count>1||forecast?{reject_existing:true}:{}) ,...(rolling?{rolling:true}:{}) ,...(grouping?{bear_cycle_anchor:bearAnchor,bear_session_key:bearKey}:{})};
        const requestFingerprint=JSON.stringify(payload);
        if(request.current?.fingerprint!==requestFingerprint)request.current={fingerprint:requestFingerprint,key:crypto.randomUUID()};
        const result=await api.createSchedule(groupId,{...payload,request_key:request.current.key});
        onSaved(result.items[0].starts_at.slice(0,10));
      }
    }catch(e){setError(message(e));}finally{lock.current=false;setBusy(false);}
  }
  const timeType=fields.precision==="date"?"date":"datetime-local";
  return <section className="data-panel calendar-editor" aria-label="Schedule editor">
    <h2>{row?"Edit scheduled event":"Add event"}</h2>
    <p>Planning only. No attendance or result records are created.</p>{forecast&&<p>Reference forecast from confirmed state date {forecast.anchor}. Review local timing before saving. Automatic renewal is optional.</p>}
    <form onSubmit={save}>
      <fieldset disabled={busy||decision!==null} className="calendar-editor-fields">
        <label>Event type<select disabled={!!row?.cycle_id} value={row?fields.event_type:creationType(fields.event_type)} onChange={e=>changeEvent(e.target.value)}>{row?<>{eventTypeOptions.map(([v,label])=><option key={v} value={v}>{label}</option>)}{fields.event_type.startsWith("game:")&&<option value={fields.event_type}>{gameEventForCalendar(fields.event_type)?.name??fields.event_type}</option>}</>:creationEventOptions.map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
        {!row&&fields.event_type==="bear_trap"&&<button type="button" className="button button--quiet" onClick={onBear}>Use multi-trap editor</button>}
        {!row&&["foundry","canyon"].includes(fields.event_type)&&onCycle&&<button type="button" className="button button--quiet" onClick={()=>onCycle(fields.event_type as CycleKind)}>Use full event cycle</button>}
        <label>Schedule owner<select disabled={!!row?.cycle_id} required value={fields.scope==="alliance"?fields.alliance_id??"":"state:"+fields.state_id} onChange={e=>changeOwner(e.target.value)}><option value="" disabled>Choose owner</option>{active.map(a=><option key={a.id} value={a.id}>{a.tag} · #{a.state_id}</option>)}{states.map(s=><option key={s} value={"state:"+s}>State #{s}</option>)}</select></label>
        {!row&&localTemplates.length>0&&<label>Saved alliance template<select value="" onChange={e=>applyTemplate(e.target.value)}><option value="">Choose a template</option>{localTemplates.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
        {!row&&followType(fields.event_type)&&<button type="button" className="button button--quiet" onClick={()=>onFollow(fields.event_type)}>Follow parent event instead</button>}
        {!row&&reference?.id==="hall-of-chief"&&<label>Event season<select value={fields.phase} onChange={e=>{setAutoEnd(true);setFields(old=>{const next={...old,phase:e.target.value};return {...next,ends_at:referenceEnd(reference,next)};});}}><option value="">Choose season</option><option value="Season 1">Season 1</option><option value="Season 2">Season 2</option></select></label>}
        {!row&&reference?.id==="frostfire-mine"&&<label>Game time slot (UTC)<select value={fields.precision==="minute"?fields.starts_at.slice(11,16):""} onChange={e=>{const time=e.target.value;if(!time)return;setAutoEnd(true);setFields(old=>{const next={...old,precision:"minute" as const,starts_at:(old.starts_at.slice(0,10)||day)+"T"+time+"Z"};return {...next,ends_at:referenceEnd(reference,next)};});}}><option value="">Choose time slot</option>{reference.schedule?.runs?.map(r=>r.startTimeUtc&&<option key={r.startTimeUtc} value={r.startTimeUtc}>{r.startTimeUtc}</option>)}</select></label>}
        <label>Precision<select value={fields.precision} onChange={e=>changePrecision(e.target.value as ScheduleFields["precision"])}><option value="date">Date only (time not set)</option><option value="minute">Date and UTC time</option></select></label>
        <label>Starts (UTC)<input required type={timeType} value={utcInput(fields.starts_at,fields.precision)} onChange={e=>{const start=e.target.value?serializeTime(e.target.value,fields.precision):"";setFields(old=>{const next=row?moveScheduleStart(old,start):{...old,starts_at:start};return autoEnd?{...next,ends_at:referenceEnd(gameEventForCalendar(next.event_type),next)}:next;});}}/></label>
        {!row&&referenceDuration(reference,fields.event_type,fields.phase)!==null&&<div className="calendar-repeat-summary"><strong>{fields.ends_at?"Ends (exclusive): "+fields.ends_at:"End time not set"}</strong><small>{autoEnd?(fields.precision==="date"&&referenceDuration(reference,fields.event_type,fields.phase)!%1440?"Game duration; date-only covers occupied dates. Choose UTC time for the exact end.":"From game reference; verify local timing."):"Manual end override."}</small>{!autoEnd&&<button type="button" className="button button--quiet" onClick={()=>{setAutoEnd(true);setFields(old=>({...old,ends_at:referenceEnd(reference,old)}));}}>Use game duration</button>}</div>}
        {!row&&<div className="calendar-repeat-summary"><strong>{count>1?count+" occurrences · "+(repeatMode==="fixed"?"Every "+days+" "+intervalUnit:repeatMode==="months"?"Every "+months+" calendar month"+(months===1?"":"s"):"Selected weekdays"):"One-time event"}</strong><div className="calendar-controls">{(suggested!==null||referencePlan.count>1)&&<button type="button" className="button button--quiet" onClick={useReference}>{referencePlan.mode==="months"?"Use monthly estimate":"Use game repeat rule"}</button>}<button type="button" className="button button--quiet" onClick={()=>{setCount(1);setReviewed(null);setGroupBear(false);}}>One-time event</button></div>{count>1&&repeatMode==="fixed"&&minutes>=1440&&count<=60&&<label className="calendar-checkbox"><input type="checkbox" checked={renew} onChange={e=>setRenew(e.target.checked)}/>Keep schedule up to date automatically</label>}<small>{rolling?"Automatically extends the estimated schedule 60 days ahead.":"Finite series. Future dates are estimates."}</small></div>}
        <button type="button" className="button button--quiet calendar-advanced-toggle" aria-expanded={advanced} onClick={()=>setAdvanced(v=>!v)}>{advanced?"Hide advanced settings":"Advanced settings"}</button>
        {advanced&&<><label>Ends (UTC, optional, exclusive)<input type={timeType} value={utcInput(fields.ends_at??"",fields.precision)} onChange={e=>{setAutoEnd(false);patch({ends_at:e.target.value?serializeTime(e.target.value,fields.precision):null});}}/></label>
        {(!!row||reference?.id!=="hall-of-chief")&&<label>Phase (optional)<input disabled={!!row?.cycle_id} maxLength={80} value={fields.phase} onChange={e=>patch({phase:e.target.value})}/></label>}
        <label>Confidence<select aria-label="Confidence" value={fields.confidence} onChange={e=>patch({confidence:e.target.value as ScheduleFields["confidence"]})}><option value="confirmed">Confirmed</option><option value="estimated">Estimated</option></select></label>
        {row?<label>Schedule status<select value={status} onChange={e=>setStatus(e.target.value as CalendarOccurrence["schedule_status"])}><option value="scheduled">Scheduled</option><option value="cancelled">Cancelled</option></select></label>:<>
        <label>Occurrences (including first)<input type="number" min={1} max={180} required value={count} onChange={e=>setCount(Number(e.target.value))}/></label>
        {count>1&&<label>Repeat pattern<select value={repeatMode} onChange={e=>setRepeatMode(e.target.value as RepeatMode)}><option value="fixed">Fixed interval</option><option value="months">Calendar months</option><option value="weekdays">Selected weekdays</option></select></label>}
        {count>1&&repeatMode==="months"&&<label>Repeat every (months)<input type="number" min={1} max={12} value={months} onChange={e=>setMonths(Number(e.target.value))}/></label>}
        {count>1&&repeatMode==="weekdays"&&<div><strong>UTC weekdays</strong>{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map((name,i)=><label key={name}><input type="checkbox" checked={weekdays.includes(i)} onChange={e=>setWeekdays(old=>e.target.checked?[...old,i]:old.filter(d=>d!==i))}/>{name}</label>)}</div>}
        {count>1&&repeatMode==="fixed"&&<><label>Repeat every ({intervalUnit})<input type="number" min={1} step={intervalUnit==="hours"?"any":1} required value={days} onChange={e=>setDays(Number(e.target.value))}/></label><label>Repeat unit<select value={intervalUnit} onChange={e=>setIntervalUnit(e.target.value as typeof intervalUnit)}><option value="days">Days</option><option value="hours">Hours</option><option value="minutes">Minutes</option></select></label></>}
        {fields.event_type==="bear_trap"&&fields.scope==="alliance"&&<div className="calendar-repeat-summary"><label className="calendar-checkbox"><input type="checkbox" checked={groupBear} onChange={e=>{setGroupBear(e.target.checked);if(e.target.checked&&count<2){setCount(4);setRepeatMode("fixed");setDays(2);setIntervalUnit("days");}}}/>Group recurring Bear traps</label>{groupBear&&<><p>Use the same first cycle start and repeat interval for related traps in all alliances. Assign a different trap identity to each series. Cycle start is not the time of every trap.</p><label>Shared first Bear cycle (UTC)<input type="datetime-local" value={bearAnchor.slice(0,16)} onChange={e=>setBearAnchor(e.target.value?e.target.value+"Z":"")}/></label><label>Trap identity<select aria-label="Trap identity" value={bearKey} onChange={e=>setBearKey(e.target.value)}><option value="">Choose explicitly</option>{Array.from({length:30},(_,i)=><option key={i} value={"trap_"+(i+1)}>Trap {i+1}</option>)}</select></label></>}</div>}
        <label>State start date (optional, reference only)<input type="date" value={stateStart} onChange={e=>setManualDate({stateId:fields.state_id,value:e.target.value})}/></label>
        </>}
        </>}
      </fieldset>
      {!row&&<>
        {advanced&&fields.scope==="alliance"&&<section className="calendar-series-preview" aria-label="Alliance templates"><h3>Alliance templates</h3><p>Save the current event type, UTC time, duration and repeat pattern for reuse. Saving a template does not schedule an event.</p><div className="calendar-editor-fields"><label>Template name<input maxLength={80} value={templateName} onChange={e=>setTemplateName(e.target.value)} disabled={busy}/></label><button type="button" className="button button--secondary" disabled={busy||!templateName.trim()||!!previewError||!fields.alliance_id} onClick={()=>void saveTemplate()}>Save as template</button></div>{localTemplates.map(t=><div key={t.id} className="calendar-controls"><span>{t.name}</span><button type="button" className="button button--quiet" disabled={busy} onClick={()=>void deleteTemplate(t)} aria-label={"Delete template "+t.name}>Delete</button></div>)}</section>}
        {templateError&&<p role="alert">{templateError}</p>}{templateMessage&&<p role="status">{templateMessage}</p>}
        {advanced&&<><p>State #{fields.state_id} · {profile?.source==="whiteoutstats"?"WhiteoutStats":profile?.source==="manual"?"Saved manual date":"Opening date unavailable"}{profile?.age_days!=null?" · "+profile.age_days+" days old":""}{profile?.last_success_at?" · Last received "+profile.last_success_at:""}{profile?.last_status==="failed"?" · Provider refresh failed; cached date retained":""}</p>
        {profile&&<div className="calendar-controls"><button type="button" className="button button--quiet" disabled={busy||!stateStart} onClick={()=>void saveStateDate(false)}>Save state date override</button>{profile.manual_opened_on&&<button type="button" className="button button--quiet" disabled={busy} onClick={()=>void saveStateDate(true)}>Use provider date</button>}</div>}
        {profileError&&<p role="alert">{profileError}</p>}
        {reference&&<div className="game-catalog-summary"><strong>Game reference</strong><p>{eventRepeatLabel(reference)} · {reference.duration??"Duration unavailable"}</p>{reference.unlockDay!==undefined&&<p>Reference unlock: state day {reference.unlockDay}{age!==null?" · Anchor age: "+age+" days":""}</p>}
          {warnings.map(w=><p key={w}>{w}</p>)}
          <small>Verify the anchor, local rotation and end time. Game reference does not confirm actual dates.</small></div>}</>}
        {!advanced&&<>{reference&&<p>Game reference: {eventRepeatLabel(reference)} · {reference.duration??"Duration not specified"}</p>}{warnings.map(w=><p key={w}>{w}</p>)}</>}
        {count>1&&<div className="calendar-series-preview"><h3>Proposed schedule</h3><p>Future occurrences are estimated. Maximum horizon: 366 days.</p>
          {previewError?<p role="alert">{previewError}</p>:<ul>{preview.map((r,i)=><li key={r.start}>{r.start}{r.end?" — "+r.end:""} · {r.confidence}{cycleDates[i]?" · Cycle "+cycleDates[i]+" · "+bearKey.replaceAll("_"," "):""}</li>)}</ul>}
          <label className="calendar-checkbox"><input type="checkbox" disabled={busy||!!previewError} checked={reviewed===fingerprint} onChange={e=>setReviewed(e.target.checked?fingerprint:null)}/>I reviewed these dates and confirmed the local repeat pattern</label>
        </div>}
      </>}
      {decision&&<section className="calendar-series-preview" aria-label="Recurring event changes">
        <h3>{status==="cancelled"?"Cancel recurring event":"Edit recurring event"}</h3>
        <fieldset disabled={busy}>
          <label><input type="radio" name="edit-scope" checked={editScope==="single"} onChange={()=>setEditScope("single")}/>This event only</label>
          <label><input type="radio" name="edit-scope" checked={editScope==="future"} onChange={()=>setEditScope("future")}/>This and following events</label>
          {editScope==="future"&&status!=="cancelled"&&decision.interval_minutes!==null&&<label>Repeat every (hours)<input type="number" min={1} max={8760} step="any" value={editHours} onChange={e=>setEditHours(Number(e.target.value))}/></label>}
        </fieldset>
        {editScope==="future"&&<><p>{decision.items.length} scheduled occurrences affected. Past events, linked records, cancelled dates and other manual exceptions are protected. {status==="cancelled"?"Automatic renewal will stop.":"Automatic renewal uses the updated time and interval."}</p>
          {row?.event_type==="bear_trap"&&row.entry_cycle_date&&<p>Shared Bear cycle identities are retained for time changes. Cadence changes are rejected if other traps share the cycle or exceptions require review.</p>}
          {editError?<p role="alert">{editError}</p>:<ul>{decision.items.map((r,i)=><li key={r.id}>{r.starts_at}{status==="cancelled"?" · Cancelled":" → "+editedDates[i]?.start+(editedDates[i]?.end?" — "+editedDates[i].end:"")}</li>)}</ul>}</>}
        <button type="button" className="button button--quiet" disabled={busy} onClick={()=>{setDecision(null);setError("");}}>Back to editing</button>
      </section>}
      {error&&<p role="alert">{error}</p>}
      <div className="calendar-controls"><button className="button button--primary" disabled={busy||!active.length||!fields.starts_at||!!editError||(!row&&(!!previewError||(count>1&&reviewed!==fingerprint)))} type="submit">{busy?"Saving…":decision?"Save changes":"Save schedule"}</button><button type="button" className="button button--quiet" disabled={busy} onClick={()=>{if(allowNavigation())onClose();}}>Close editor</button></div>
    </form>
  </section>;
}
