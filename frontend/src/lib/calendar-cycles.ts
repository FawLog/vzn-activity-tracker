import {addDays} from "./calendar";
import {gameEventForCalendar,type GameRun} from "./game-event-catalog";
import {fixedGameInterval,runMinutes,referenceEnd} from "./game-forecast";
import type {ScheduleFields} from "./schedule-editor";
export type CycleKind="canyon"|"svs";
export type CycleCreate={kind:CycleKind;request_key:string;phases:ScheduleFields[];occurrence_count?:number;interval_days?:number};
const weekdays=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"];
export function cycleReference(kind:CycleKind){return gameEventForCalendar(kind==="canyon"?"canyon":"svs_preparation");}
export function cycleIntervalDays(kind:CycleKind):number|null{
  const n=fixedGameInterval(cycleReference(kind));
  return n!==null&&n%1440===0?n/1440:null;
}
function offset(run:GameRun):number{
  const d=weekdays.indexOf(run.startWeekday?.toLowerCase()??"");
  if(d<0)throw Error("Game reference is missing the phase weekday; review the catalog.");
  return d;
}
export function cycleDraft(kind:CycleKind,monday:string,state:string,alliance:string|null):ScheduleFields[]{
  const day=new Date(monday+"T00:00Z");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(monday)||!Number.isFinite(day.getTime())||day.toISOString().slice(0,10)!==monday||day.getUTCDay()!==1)throw Error("Choose a Monday UTC anchor");
  const reference=cycleReference(kind);
  const runs=reference?.schedule?.runs??[];
  const common={scope:kind==="canyon"?"alliance" as const:"state" as const,alliance_id:kind==="canyon"?alliance:null,state_id:state,confidence:"estimated" as const};
  const find=(label:string)=>{
    const run=runs.find(r=>r.label===label);
    if(!run||runMinutes(run)===null)throw Error("Game reference is missing "+label+" timing.");
    return run;
  };
  if(kind==="canyon")return ["Voting","Registration","Matchmaking","Battle"].map(phase=>{
    const run=find(phase),start=addDays(monday,offset(run)),n=runMinutes(run)!;
    if(phase==="Battle")return {...common,event_type:"canyon",phase,precision:"date",starts_at:start,ends_at:null};
    if(n%1440===0)return {...common,event_type:"canyon",phase,precision:"date",starts_at:start,ends_at:addDays(start,n/1440)};
    const row:ScheduleFields={...common,event_type:"canyon",phase,precision:"minute",starts_at:start+"T"+(run.startTimeUtc??"00:00")+"Z",ends_at:null};
    return {...row,ends_at:new Date(Date.parse(row.starts_at)+n*60000).toISOString().slice(0,16)+"Z"};
  });
  const prep=find("Preparation"),battle=find("Battle");
  if(!battle.startTimeUtc)throw Error("Game reference is missing SvS battle start time.");
  const start=addDays(monday,offset(prep))+"T"+(prep.startTimeUtc??"00:00")+"Z";
  const battleStart=addDays(monday,offset(battle))+"T"+battle.startTimeUtc+"Z";
  const battleRow:ScheduleFields={...common,event_type:"svs_battle",phase:"Battle",precision:"minute",starts_at:battleStart,ends_at:null};
  // Keep the reviewed policy: preparation continues until the known battle start.
  return [{...common,event_type:"svs_preparation",phase:"Preparation",precision:"minute",starts_at:start,ends_at:battleStart},
    {...battleRow,ends_at:referenceEnd(reference,battleRow)}];
}
export function canyonBattleEnd(fields:ScheduleFields):string|null{
  return fields.event_type==="canyon"&&fields.phase==="Battle"?referenceEnd(cycleReference("canyon"),fields):null;
}
export function cycleOccurrences(kind:CycleKind,phases:ScheduleFields[],count:number,interval:number):ScheduleFields[][]{
  if(!Number.isInteger(count)||count<1||count>14||!Number.isInteger(interval)||interval<1||(count-1)*interval>366)throw Error("Choose up to 14 cycles within 366 days.");
  if(!phases.length)return [];
  const time=(p:ScheduleFields,value:string)=>Date.parse(p.precision==="date"?value+"T00:00Z":value);
  if(phases.some(p=>!Number.isFinite(time(p,p.starts_at))||p.ends_at!==null&&(!Number.isFinite(time(p,p.ends_at))||time(p,p.ends_at)<=time(p,p.starts_at))))throw Error("Enter valid phase dates.");
  if(phases.some((p,i)=>i>0&&(time(p,p.starts_at)<=time(phases[i-1],phases[i-1].starts_at)||!!phases[i-1].ends_at&&time(p,p.starts_at)<time(phases[i-1],phases[i-1].ends_at!))))throw Error("Phases must be chronological and must not overlap.");
  const first=time(phases[0],phases[0].starts_at),last=phases[phases.length-1];
  if(count>1&&time(last,last.ends_at??last.starts_at)>=first+interval*86400000)throw Error("Repeat interval must exceed the cycle duration.");
  return Array.from({length:count},(_,i)=>phases.map(p=>{
    if(i===0)return p;
    const move=(v:string)=>addDays(v.slice(0,10),i*interval)+v.slice(10);
    if(kind==="canyon"&&p.phase==="Battle")return {...p,starts_at:move(p.starts_at).slice(0,10),ends_at:null,precision:"date",confidence:"estimated"};
    return {...p,starts_at:move(p.starts_at),ends_at:p.ends_at?move(p.ends_at):null,confidence:"estimated"};
  }));
}
