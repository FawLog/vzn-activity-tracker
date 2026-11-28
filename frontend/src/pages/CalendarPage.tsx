import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ScheduleEditor, FutureScheduleEditor } from "../components/ScheduleEditor";
import { GameEventCatalog, EventCatalogSummary } from "../components/GameEventCatalog";
import { gameEventForCalendar } from "../lib/game-event-catalog";
import { EventStageTimeline } from "../components/EventStageTimeline";
import { eventDay, stagesOn } from "../lib/calendar-stages";
import { EventIcon } from "../components/EventIcon";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { calendarRange, calendarTime, moveCalendar, occursOn, utcDay, addDays, type CalendarOccurrence, type CalendarView } from "../lib/calendar";
import { eventLabel, formatDate } from "../lib/format";
import { useGroupContext } from "../lib/group-context";

const views:CalendarView[]=["Agenda","Week","Month"];
const weekday=(day:string)=>new Intl.DateTimeFormat("en",{weekday:"short",timeZone:"UTC"}).format(new Date(day+"T00:00:00Z"));
const monthLabel=(day:string)=>new Intl.DateTimeFormat("en",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(day+"T00:00:00Z"));

export function CalendarPage(){
  const {selectedGroup,alliances,selectedAlliance}=useGroupContext();
  const groupId=selectedGroup?.id;
  const [showCatalog,setShowCatalog]=useState(false);
  const [day,setDay]=useState(()=>utcDay());
  const [view,setView]=useState<CalendarView>(()=>window.matchMedia("(max-width: 700px)").matches?"Agenda":"Week");
  const [scope,setScope]=useState("all");
  const [showCancelled,setShowCancelled]=useState(false);
  const [loaded,setLoaded]=useState<{key:string;items:CalendarOccurrence[]}|null>(null);
  const [failure,setFailure]=useState<{key:string;message:string}|null>(null);
  const [retry,setRetry]=useState(0);
  const [editor,setEditor]=useState<{groupId:string;row:CalendarOccurrence|null;future:boolean}|null>(null);
  const [detail,setDetail]=useState<{groupId:string;row:CalendarOccurrence}|null>(null);
  const {start,end,days}=calendarRange(day,view);
  const key=groupId+"|"+start+"|"+end+"|"+retry;
  useEffect(()=>{
    if(!groupId||!selectedGroup)return;
    const controller=new AbortController();
    api.calendar(groupId,start,end,controller.signal).then(result=>{
      if(!controller.signal.aborted)setLoaded({key,items:result.items});
    }).catch(error=>{
      if(!controller.signal.aborted)setFailure({key,message:error instanceof Error?error.message:"Unable to load calendar"});
    });
    return ()=>controller.abort();
  },[groupId,start,end,key]);
  const items=loaded?.key===key?loaded.items:null;
  const error=failure?.key===key?failure.message:"";
  const visible=(items??[]).filter(row=>(showCancelled||row.schedule_status!=="cancelled") &&
    (scope==="all"||(scope==="state"?row.scope==="state":row.scope==="alliance"&&row.alliance_id===selectedAlliance?.id)));
  const owner=(row:CalendarOccurrence)=>row.scope==="state"?"State #"+row.state_id:(alliances.find(a=>a.id===row.alliance_id)?.tag??"Alliance")+" · #"+row.state_id;
  const status=(row:CalendarOccurrence)=>row.schedule_status==="cancelled"?"Cancelled":row.confidence==="confirmed"?"Confirmed":"Estimated";
  const changeDay=(next:string)=>{setDay(next);setDetail(null);};
  if(!groupId)return <div className="page"><EmptyState title="No active group" description="Select a group to view its schedule."/></div>;
  const selected=detail?.groupId===groupId?detail.row:null;
  const editing=editor?.groupId===groupId?editor:null;
  const reference=selected?gameEventForCalendar(selected.event_type):undefined;
  const writable=selectedGroup.status==="active"&&alliances.some(a=>a.group_id===groupId&&a.status==="active");
  const saved=(next?:string)=>{setEditor(null);setDetail(null);if(next)setDay(next);setScope("all");setRetry(n=>n+1);};
  return <div className="page calendar-page">
    <PageHeader title="Event Calendar" description={selectedGroup.name+" · Planned events only · All times UTC"}/>
    <div className="toolbar calendar-toolbar">
      <button className="button button--quiet" aria-expanded={showCatalog} onClick={()=>setShowCatalog(v=>!v)}>Game event catalog</button>
      {writable&&<button className="button button--primary" onClick={()=>{setDetail(null);setEditor({groupId,row:null,future:false});}}>Add scheduled event</button>}
      <div className="calendar-controls" aria-label="Calendar view">{views.map(mode=><button key={mode} className={"button "+(view===mode?"button--primary":"button--quiet")} aria-pressed={view===mode} onClick={()=>{setView(mode);setDetail(null);}}>{mode}</button>)}</div>
      <div className="calendar-controls"><button className="icon-button" aria-label="Previous period" onClick={()=>changeDay(moveCalendar(day,view,-1))}><ChevronLeft/></button><button className="button button--quiet" onClick={()=>changeDay(utcDay())}>Today</button><button className="icon-button" aria-label="Next period" onClick={()=>changeDay(moveCalendar(day,view,1))}><ChevronRight/></button></div>
      <label className="select-control">Scope<select value={scope} onChange={e=>{setScope(e.target.value);setDetail(null);}}><option value="all">All events</option><option value="alliance">Current alliance</option><option value="state">State events</option></select></label>
      <label className="calendar-checkbox"><input type="checkbox" checked={showCancelled} onChange={e=>{setShowCancelled(e.target.checked);setDetail(null);}}/>Show cancelled</label>
    </div>
    {showCatalog&&<GameEventCatalog onClose={()=>setShowCatalog(false)}/>}
    {editing&&writable&&(editing.future&&editing.row?<FutureScheduleEditor key={groupId+editing.row.id+"future"} groupId={groupId} row={editing.row} onClose={()=>setEditor(null)} onSaved={()=>saved()}/>:<ScheduleEditor key={groupId+(editing.row?.id??"new")} groupId={groupId} alliances={alliances} preferred={selectedAlliance?.id} day={day} row={editing.row} onClose={()=>setEditor(null)} onSaved={saved}/>)}
    <h2 className="calendar-period">{view==="Month"?monthLabel(day):formatDate(start)+" – "+formatDate(addDays(end,-1))}</h2>
    {error?<ErrorState message={error} action={<button className="button button--quiet" onClick={()=>setRetry(n=>n+1)}>Retry</button>}/>:!items?<LoadingState label="Loading schedule"/>:
    <section className={"data-panel calendar-schedule calendar-schedule--"+view.toLowerCase()} aria-label={view+" schedule"}>
      {view!=="Agenda"&&<div className="calendar-weekdays" aria-hidden="true">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d=><span key={d}>{d}</span>)}</div>}
      <div className="calendar-days">{days.map(date=>{
        const events=visible.filter(row=>occursOn(row,date));
        return <section key={date} className={"calendar-day"+(view==="Month"&&date.slice(0,7)!==day.slice(0,7)?" calendar-day--outside":"")+(date===utcDay()?" calendar-day--today":"")} aria-label={formatDate(date)}>
          <h3>{view==="Month"?Number(date.slice(8)):weekday(date)+" "+formatDate(date)}</h3>
          {events.map(row=><button key={row.id} className={"calendar-entry calendar-entry--"+(row.schedule_status==="cancelled"?"cancelled":row.confidence)} onClick={()=>setDetail({groupId,row})}>
            <EventIcon eventType={row.event_type}/><span className="calendar-entry-copy"><strong>{(gameEventForCalendar(row.event_type)?.name&&row.event_type.startsWith("game:")?gameEventForCalendar(row.event_type)?.name:eventLabel(row.event_type))}</strong>{row.phase&&<span>{row.phase}</span>}{eventDay(row,date)&&<small className="calendar-day-number">{eventDay(row,date)}</small>}{stagesOn(row,date).map(stage=><small className="calendar-stage-label" key={stage.id}>{stage.name} · Est.</small>)}<small>{calendarTime(row,date)}</small><small>{owner(row)} · {status(row)}</small></span>
          </button>)}
          {!events.length&&view!=="Month"&&<small className="calendar-empty">No scheduled events</small>}
        </section>;
      })}</div>
    </section>}
    {selected&&<section className="data-panel calendar-detail" aria-label="Schedule details">
      <div className="calendar-controls"><EventIcon eventType={selected.event_type}/><h2>{(selected.event_type.startsWith("game:")?reference?.name??eventLabel(selected.event_type):eventLabel(selected.event_type))}</h2><button className="button button--quiet" onClick={()=>setDetail(null)}>Close details</button></div>
      <p>{owner(selected)} · {status(selected)}{selected.phase?" · "+selected.phase:""}</p>
      <p>{formatDate(selected.starts_at)} · {calendarTime(selected,selected.starts_at.slice(0,10))}{selected.ends_at?" — until "+formatDate(selected.ends_at)+(selected.precision==="minute"?" "+selected.ends_at.slice(11,16)+" UTC":" (exclusive)"):""}</p>
      {writable&&<div className="calendar-controls"><button className="button button--quiet" onClick={()=>{setEditor({groupId,row:selected,future:false});setDetail(null);}}>Edit schedule</button>{selected.series_id&&selected.schedule_status==="scheduled"&&selected.starts_at.slice(0,10)>=utcDay()&&<button className="button button--quiet" onClick={()=>{setEditor({groupId,row:selected,future:true});setDetail(null);}}>Change future series</button>}</div>}
      <EventStageTimeline key={selected.id} row={selected}/>
      {reference&&<details><summary>Game reference</summary><EventCatalogSummary event={reference}/></details>}
      <p>Source: {selected.source==="manual"?"Manual schedule":"Recurring forecast"}{selected.series_id?" · Recurring series":""}</p>
    </section>}
  </div>;
}
