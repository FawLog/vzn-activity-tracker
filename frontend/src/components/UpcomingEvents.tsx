import {useEffect,useState} from "react";
import {api} from "../lib/api";
import {addDays,utcDay,type CalendarOccurrence} from "../lib/calendar";
import {upcomingEvents,upcomingTiming,upcomingCalendarUrl} from "../lib/upcoming-events";
import {gameEventForCalendar} from "../lib/game-event-catalog";
import {eventLabel,formatDate} from "../lib/format";
import {navigate} from "../lib/router";
import type {Alliance} from "../lib/types";
import {EventIcon} from "./EventIcon";
import {SectionHeader} from "./Page";

export function UpcomingEvents({groupId,alliances,selectedAllianceId,now}:{groupId:string;alliances:Alliance[];selectedAllianceId?:string;now:number}){
  const [scope,setScope]=useState("alliance");
  const [retry,setRetry]=useState(0);
  const [loaded,setLoaded]=useState<{key:string;items:CalendarOccurrence[]}|null>(null);
  const [failure,setFailure]=useState<{key:string;message:string}|null>(null);
  const today=utcDay(new Date(now));
  const key=groupId+"|"+today+"|"+retry;
  useEffect(()=>{
    const controller=new AbortController();
    api.calendar(groupId,today,addDays(today,7),controller.signal).then(r=>{if(!controller.signal.aborted)setLoaded({key,items:r.items});}).catch(e=>{if(!controller.signal.aborted)setFailure({key,message:e instanceof Error?e.message:"Unable to load schedule"});});
    return ()=>controller.abort();
  },[groupId,today,key]);
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const relevant=scope==="group"?active:active.filter(a=>a.id===selectedAllianceId);
  const list=upcomingEvents(loaded?.key===key?loaded.items:[],now,groupId,new Set(relevant.map(a=>a.id)),new Set(relevant.map(a=>a.state_id)));
  const error=failure?.key===key?failure.message:"";
  return <section className="data-panel upcoming-events" aria-label="Upcoming events">
    <SectionHeader title="Upcoming events" description="Next 7 UTC calendar days · Planned schedule" action={<button className="button button--quiet" onClick={()=>navigate("/calendar")}>Open calendar</button>}/>
    <div className="upcoming-controls"><label>Schedule scope<select value={scope} onChange={e=>setScope(e.target.value)}><option value="alliance">Current alliance and state</option><option value="group">All group alliances and states</option></select></label><button className="button button--quiet" onClick={()=>setRetry(n=>n+1)}>Refresh schedule</button></div>
    {error?<p role="alert">{error}</p>:loaded?.key!==key?<p>Loading upcoming events…</p>:!list.length?<p>No scheduled events in this period. Missing schedules do not mean no game events.</p>:<ul className="upcoming-list">{list.slice(0,6).map(r=><li key={r.id}><button className="upcoming-row" onClick={()=>navigate(upcomingCalendarUrl(r,now))}>
      <EventIcon eventType={r.event_type}/><span className="upcoming-name"><strong>{r.event_type.startsWith("game:")?gameEventForCalendar(r.event_type)?.name??eventLabel(r.event_type):eventLabel(r.event_type)}</strong><small>{r.phase?r.phase+" · ":""}{r.scope==="state"?"State #"+r.state_id:(active.find(a=>a.id===r.alliance_id)?.tag??"Alliance")+" · #"+r.state_id}</small><small>{formatDate(r.starts_at)}{r.precision==="minute"?" · "+r.starts_at.slice(11,16)+" UTC":""}{r.review?" · Record: "+r.review.publication:""}</small></span><span className="upcoming-time"><strong>{upcomingTiming(r,now)}</strong><small className={r.confidence==="estimated"?"upcoming-estimated":""}>{r.confidence==="estimated"?"Estimated":"Confirmed"}</small></span>
    </button></li>)}</ul>}
    {list.length>6&&<p className="upcoming-more">{list.length-6} more in calendar</p>}
  </section>;
}
