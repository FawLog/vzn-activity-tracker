import {gameEventForCalendar,stateTimeline,type StateMilestone} from "./game-event-catalog";
import {fixedGameInterval,runForType,forecastRows,stateAge} from "./game-forecast";
import {addDays,type CalendarOccurrence} from "./calendar";
import type {ScheduleFields} from "./schedule-editor";

// These rules have explicit whole-day fixed cadences in v0.11.0. Other events
// need a local anchor plus a reviewed rotation rule, not a guessed 30-day month.
export const rotationTypes=["game:lucky-wheel","game:hall-of-heroes","game:heros-mission","svs_preparation","svs_battle"] as const;
export type RotationForecast={fields:ScheduleFields;interval:number;count:number;anchor:string};
export type RotationReview={type:string;name:string;forecast?:RotationForecast;reason?:string};
export function progression(opened:string,today:string,horizon=60,timeline:readonly StateMilestone[]=stateTimeline){
  const age=stateAge(opened,today);
  const generations=timeline.filter(m=>m.heroIds.length);
  const currentGeneration=generations.filter(m=>m.day<=age).length;
  return {age,currentGeneration,nextGeneration:generations.find(m=>m.day>age),upcoming:timeline.filter(m=>m.day>age&&m.day<=age+horizon).map(m=>({...m,date:addDays(opened,m.day)}))};
}
const phaseMatches=(type:string,phase:string)=>type==="svs_preparation"?["","preparation"].includes(phase.trim().toLowerCase()):type==="svs_battle"?["","battle"].includes(phase.trim().toLowerCase()):phase.trim()==="";
const millis=(row:CalendarOccurrence)=>Date.parse(row.precision==="date"?row.starts_at+"T00:00Z":row.starts_at);
export function reviewRotation(rows:readonly CalendarOccurrence[],stateId:string,opened:string,today:string,horizon=60):RotationReview[]{
  const age=stateAge(opened,today),todayMs=Date.parse(today+"T00:00Z"),limit=todayMs+horizon*86400000;
  return rotationTypes.map(type=>{
    const ref=gameEventForCalendar(type),name=type==="svs_preparation"?"SvS · Preparation":type==="svs_battle"?"SvS · Battle":ref?.name??type;
    const skip=(reason:string)=>({type,name,reason});
    const interval=fixedGameInterval(ref);
    if(!ref||interval===null||interval%1440)return skip("No reviewed fixed-day rule");
    if(ref.unlockDay!==undefined&&age<ref.unlockDay)return skip("Reference unlock has not been reached");
    const relevant=rows.filter(r=>r.state_id===stateId&&r.event_type===type);
    // Do not fill holes in an existing calendar or recreate cancellations.
    if(relevant.some(r=>r.starts_at.slice(0,10)>=today))return skip("Upcoming or cancelled schedule already exists; review it instead");
    const anchors=relevant.filter(r=>r.scope==="state"&&r.confidence==="confirmed"&&r.schedule_status==="scheduled"&&phaseMatches(type,r.phase)&&r.starts_at.slice(0,10)<today)
      .sort((a,b)=>b.starts_at.localeCompare(a.starts_at));
    const anchor=anchors[0];
    if(!anchor)return skip("Needs a confirmed state-level date in the last 90 days");
    if(todayMs-millis(anchor)>91*86400000)return skip("Confirmed anchor is too old");
    if(ref.unlockDay!==undefined&&stateAge(opened,anchor.starts_at)<ref.unlockDay)return skip("Anchor predates the reference unlock; verify local availability");
    const run=runForType(ref,type);
    const weekday=["sunday","monday","tuesday","wednesday","thursday","friday","saturday"][new Date(millis(anchor)).getUTCDay()];
    if(run?.startWeekday&&weekday!==run.startWeekday.toLowerCase())return skip("Confirmed weekday differs from the reference");
    if(run?.startTimeUtc&&anchor.precision==="minute"&&anchor.starts_at.slice(11,16)!==run.startTimeUtc)return skip("Confirmed time differs from the reference");
    const step=interval*60000;
    if(anchors.some(a=>{
      const delta=Date.parse(anchor.starts_at.slice(0,10))-Date.parse(a.starts_at.slice(0,10));
      return delta%step!==0||(a.precision==="minute"&&anchor.precision==="minute"&&a.starts_at.slice(11,16)!==anchor.starts_at.slice(11,16));
    }))return skip("Confirmed dates disagree with the reference cadence");
    const first=millis(anchor)+Math.max(1,Math.ceil((todayMs-millis(anchor))/step))*step;
    // Today may already be underway. Never propose a new occurrence today.
    const start=first<todayMs+86400000?first+step:first;
    if(start>limit)return skip("Next reference date is outside the forecast window");
    const count=Math.floor((limit-start)/step)+1;
    const format=(ms:number)=>new Date(ms).toISOString().slice(0,anchor.precision==="date"?10:16)+(anchor.precision==="minute"?"Z":"");
    const duration=anchor.ends_at?Date.parse(anchor.precision==="date"?anchor.ends_at+"T00:00Z":anchor.ends_at)-millis(anchor):null;
    const fields:ScheduleFields={event_type:type,scope:"state",alliance_id:null,state_id:stateId,phase:anchor.phase,precision:anchor.precision,starts_at:format(start),ends_at:duration===null?null:format(start+duration),confidence:"estimated"};
    try{forecastRows(fields,count,interval);}catch{return skip("Forecast dates require manual review");}
    return {type,name,forecast:{fields,interval,count,anchor:anchor.starts_at}};
  });
}
