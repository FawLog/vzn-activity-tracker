import {useEffect,useState} from "react";
import {api,type StateCalendarProfile} from "../lib/api";
import {addDays,utcDay,type CalendarOccurrence} from "../lib/calendar";
import {catalogVersion,gameEvents} from "../lib/game-event-catalog";
import {progression,reviewRotation,type RotationForecast} from "../lib/state-rotation";
const label=(id:string)=>id.split("-").map(word=>word.charAt(0).toUpperCase()+word.slice(1)).join(" ");
type Data={profiles:StateCalendarProfile[];rows:CalendarOccurrence[];today:string};
export function StateForecastPanel({groupId,preferredState,writable,onClose,onReview}:{groupId:string;preferredState?:string;writable:boolean;onClose:()=>void;onReview:(forecast:RotationForecast)=>void}){
  const [data,setData]=useState<Data|null>(null);
  const [error,setError]=useState("");
  const [state,setState]=useState(preferredState??"");
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    const controller=new AbortController(),today=utcDay();
    setData(null);setError("");
    Promise.all([api.stateCalendarProfiles(groupId,controller.signal),api.calendar(groupId,addDays(today,-90),today,controller.signal),api.calendar(groupId,today,addDays(today,61),controller.signal)]).then(([profiles,past,future])=>{
      if(controller.signal.aborted)return;
      setData({profiles:profiles.items,rows:[...new Map([...past.items,...future.items].map(r=>[r.id,r])).values()],today});
      setState(old=>profiles.items.some(p=>p.state_id===old)?old:profiles.items[0]?.state_id??"");
    }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:"Unable to load state forecast");});
    return ()=>controller.abort();
  },[groupId,retry]);
  const profile=data?.profiles.find(p=>p.state_id===state);
  let progress:ReturnType<typeof progression>|null=null,reviews:ReturnType<typeof reviewRotation>=[],calculationError="";
  if(data&&profile?.opened_on){
    try{progress=progression(profile.opened_on,data.today);reviews=reviewRotation(data.rows,state,profile.opened_on,data.today);}
    catch(e){calculationError=e instanceof Error?e.message:"Invalid state date or reference data";}
  }
  const names=(ids:string[])=>ids.map(label).join(", ");
  return <section className="data-panel calendar-editor" aria-label="State progression and forecast">
    <div className="calendar-controls"><h2>State progression &amp; forecast</h2><button className="button button--quiet" onClick={onClose}>Close forecast</button></div>
    <p>Reference: Whiteout Survival Data {catalogVersion}. All dates are estimates, not live in-game schedule data.</p>
    {error?<><p role="alert">{error}</p><button className="button button--quiet" onClick={()=>setRetry(n=>n+1)}>Retry forecast</button></>:!data?<p role="status">Loading state forecast…</p>:<>
      <label>State<select aria-label="Forecast state" value={state} onChange={e=>setState(e.target.value)}>{data.profiles.map(p=><option key={p.state_id} value={p.state_id}>#{p.state_id}</option>)}</select></label>
      {!profile?.opened_on?<p>State opening date unavailable. Set an opening date in Add event / Advanced settings before forecasting.</p>:<>
        <p>Opened {profile.opened_on} · {profile.source==="manual"?"Manual override":"WhiteoutStats"}{profile.last_status==="failed"?" · Latest provider refresh failed; using cached date":""}</p>
        {calculationError&&<p role="alert">{calculationError}</p>}
        {progress&&<><h3>State day {progress.age}</h3><p>Reference hero generation: {progress.currentGeneration||"Unknown"}{progress.nextGeneration?" · Next: day "+progress.nextGeneration.day:""}</p>
          <h3>Upcoming unlocks · next 60 days</h3>
          {progress.upcoming.length===0?<p>No reference milestones within this window.</p>:<ul>{progress.upcoming.map(m=><li key={m.day}><strong>{m.date} · Day {m.day} · Estimated</strong>
            {m.heroIds.length>0&&<p>Heroes: {names(m.heroIds)}</p>}{m.petIds.length>0&&<p>Pets: {names(m.petIds)}</p>}{m.expertIds.length>0&&<p>Experts: {names(m.expertIds)}</p>}{m.fireCrystalLevelIds.length>0&&<p>Fire Crystal levels: {names(m.fireCrystalLevelIds)}</p>}{m.eventIds.length>0&&<p>Events: {m.eventIds.map(id=>gameEvents.find(e=>e.id===id)?.name??label(id)).join(", ")}</p>}
            {m.unlocks.map((u,i)=><p key={i}>{u.name}{u.requirement?" · "+u.requirement:""}</p>)}</li>)}</ul>}
          <h3>Rotation suggestions · next 60 days</h3><p>Uses confirmed state-level dates from the last 90 days. Existing upcoming or cancelled schedules take priority. No entries are created without review.</p>
          {reviews.map(r=><div key={r.type} className="calendar-repeat-summary"><strong>{r.name}</strong>{r.forecast?<><p>{r.forecast.fields.starts_at} · Estimated · {r.forecast.count} occurrences · every {r.forecast.interval/1440} days</p><small>Confirmed anchor: {r.forecast.anchor}</small>{writable&&<button className="button button--quiet" onClick={()=>onReview(r.forecast!)}>Review {r.name} forecast</button>}</>:<small>{r.reason}</small>}</div>)}
          <small>Castle, King of Icefield, Alliance Mobilization/Showdown and local alliance events need separately verified rotation rules. SvS preparation and battle forecasts are separate; verify the full cycle in game.</small>
        </>}
      </>}
    </>}
  </section>;
}
