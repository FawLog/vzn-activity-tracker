import {addDays} from "./calendar";
import {gameEventForCalendar,type GameRun} from "./game-event-catalog";
import {fixedGameInterval,runMinutes,referenceEnd} from "./game-forecast";
import type {ScheduleFields} from "./schedule-editor";
export type CycleKind="canyon"|"foundry"|"svs";
export type CycleCreate={kind:CycleKind;request_key:string;phases:ScheduleFields[];occurrence_count?:number;interval_days?:number};
const weekdays=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"];
export function cycleReference(kind:CycleKind){return gameEventForCalendar(kind==="svs"?"svs_preparation":kind);}
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
  const common={scope:kind!=="svs"?"alliance" as const:"state" as const,alliance_id:kind!=="svs"?alliance:null,state_id:state,confidence:"estimated" as const};
  const find=(label:string)=>{
    const run=runs.find(r=>r.label===label);
    if(!run||runMinutes(run)===null)throw Error("Game reference is missing "+label+" timing.");
    return run;
  };
  if(kind!=="svs")return ["Voting","Registration","Matchmaking","Battle"].map(phase=>{
    const run=find(phase),start=addDays(monday,offset(run)),n=runMinutes(run)!;
    if(phase==="Battle")return {...common,event_type:kind,phase,precision:"date",starts_at:start,ends_at:null};
    if(n%1440===0)return {...common,event_type:kind,phase,precision:"date",starts_at:start,ends_at:addDays(start,n/1440)};
    const row:ScheduleFields={...common,event_type:kind,phase,precision:"minute",starts_at:start+"T"+(run.startTimeUtc??"00:00")+"Z",ends_at:null};
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
export const isLegion=(phase:string)=>/^Legion [12]$/.test(phase);
export const isBattlePhase=(phase:string)=>phase==="Battle"||isLegion(phase);
export function canyonBattleEnd(fields:ScheduleFields):string|null{
  return ["canyon","foundry"].includes(fields.event_type)&&isBattlePhase(fields.phase)?referenceEnd(gameEventForCalendar(fields.event_type),fields):null;
}
export function legionPhases(phases:ScheduleFields[],two:boolean):ScheduleFields[]{
  const battle=phases.find(p=>isBattlePhase(p.phase));
  if(!battle)return phases;
  const prep=phases.filter(p=>!isBattlePhase(p.phase));
  const first={...battle,phase:"Legion 1"};
  return two?[...prep,first,{...first,phase:"Legion 2",precision:"date",starts_at:first.starts_at.slice(0,10),ends_at:null,confidence:"estimated"}]:[...prep,first];
}
export function cycleOccurrences(kind:CycleKind,phases:ScheduleFields[],count:number,interval:number):ScheduleFields[][]{
  if(!Number.isInteger(count)||count<1||count>14||!Number.isInteger(interval)||interval<1||(count-1)*interval>366)throw Error("Choose up to 14 cycles within 366 days.");
  if(!phases.length)return [];
  const time=(p:ScheduleFields,value:string)=>Date.parse(p.precision==="date"?value+"T00:00Z":value);
  if(phases.some(p=>!Number.isFinite(time(p,p.starts_at))||p.ends_at!==null&&(!Number.isFinite(time(p,p.ends_at))||time(p,p.ends_at)<=time(p,p.starts_at))))throw Error("Enter valid phase dates.");
  if(phases.some((p,i)=>i>0&&!(isLegion(p.phase)&&isLegion(phases[i-1].phase))&&(time(p,p.starts_at)<=time(phases[i-1],phases[i-1].starts_at)||!!phases[i-1].ends_at&&time(p,p.starts_at)<time(phases[i-1],phases[i-1].ends_at!))))throw Error("Phases must be chronological and must not overlap.");
  const battles=phases.filter(p=>isLegion(p.phase));
  if(battles.length===2){
    if(battles[0].starts_at.slice(0,10)!==battles[1].starts_at.slice(0,10))throw Error("Legions must share the same battle date.");
    if(battles.every(p=>p.precision==="minute")&&battles[0].starts_at===battles[1].starts_at)throw Error("Choose distinct legion start times.");
    const prep=phases.find(p=>p.phase==="Matchmaking");
    if(prep?.ends_at&&battles.some(p=>time(p,p.starts_at)<time(prep,prep.ends_at!)))throw Error("Battle must follow matchmaking.");
  }
  const first=time(phases[0],phases[0].starts_at);
  if(count>1&&Math.max(...phases.map(p=>time(p,p.ends_at??p.starts_at)))>=first+interval*86400000)throw Error("Repeat interval must exceed the cycle duration.");
  return Array.from({length:count},(_,i)=>phases.map(p=>{
    if(i===0)return p;
    const move=(v:string)=>addDays(v.slice(0,10),i*interval)+v.slice(10);
    if(kind!=="svs"&&isBattlePhase(p.phase))return {...p,starts_at:move(p.starts_at).slice(0,10),ends_at:null,precision:"date",confidence:"estimated"};
    return {...p,starts_at:move(p.starts_at),ends_at:p.ends_at?move(p.ends_at):null,confidence:"estimated"};
  }));
}
