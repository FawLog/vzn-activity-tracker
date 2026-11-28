import {addDays,type CalendarOccurrence} from "./calendar";
import {gameEventForCalendar,type GameRun} from "./game-event-catalog";
import {fixedGameInterval,runMinutes,referenceEnd,referenceDuration} from "./game-forecast";
import {moveScheduleStart,type ScheduleFields} from "./schedule-editor";
export type CycleKind="canyon"|"foundry"|"svs";
export type CycleCreate={kind:CycleKind;request_key:string;phases:ScheduleFields[];occurrence_count?:number;interval_days?:number;rolling?:boolean};
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
  const matchmaking=find("Matchmaking"),prep=find("Preparation"),battle=find("Battle"),triage=find("Field Triage");
  if(!battle.startTimeUtc)throw Error("Game reference is missing SvS battle start time.");
  const start=addDays(monday,offset(prep))+"T"+(prep.startTimeUtc??"00:00")+"Z";
  const battleStart=addDays(monday,offset(battle))+"T"+battle.startTimeUtc+"Z";
  const time=(ms:number)=>new Date(ms).toISOString().slice(0,16)+"Z";
  const battleEnd=time(Date.parse(battleStart)+runMinutes(battle)!*60000);
  const matchStart=time(Date.parse(start)-runMinutes(matchmaking)!*60000);
  const triageEnd=time(Date.parse(battleEnd)+runMinutes(triage)!*60000);
  return [
    {...common,event_type:"svs_matchmaking",phase:"Matchmaking",precision:"minute",starts_at:matchStart,ends_at:start},
    {...common,event_type:"svs_preparation",phase:"Preparation",precision:"minute",starts_at:start,ends_at:battleStart},
    {...common,event_type:"svs_battle",phase:"Battle",precision:"minute",starts_at:battleStart,ends_at:battleEnd},
    {...common,event_type:"svs_triage",phase:"Field Triage",precision:"minute",starts_at:battleEnd,ends_at:triageEnd}
  ];
}
export const isLegion=(phase:string)=>/^Legion [12]$/.test(phase);
export const isBattlePhase=(phase:string)=>phase==="Battle"||isLegion(phase);
export function canyonBattleEnd(fields:ScheduleFields):string|null{
  return ["canyon","foundry"].includes(fields.event_type)&&isBattlePhase(fields.phase)?referenceEnd(gameEventForCalendar(fields.event_type),fields):null;
}
// Preserve reviewed phase lengths on a start edit. When switching precision,
 // a new explicit start uses the phase-specific reference, never a made-up clock time.
export function moveCyclePhaseStart(fields:ScheduleFields,start:string):ScheduleFields{
  if(!start)return {...fields,starts_at:"",ends_at:null};
  const moved=moveScheduleStart(fields,start);
  if(fields.starts_at&&fields.ends_at)return moved;
  if(fields.starts_at&&!isBattlePhase(fields.phase))return moved;
  const event=gameEventForCalendar(fields.event_type);
  const minutes=fields.event_type.startsWith("svs_")?referenceDuration(event,fields.event_type,fields.phase):
    runMinutes(event?.schedule?.runs?.find(r=>r.label===(isBattlePhase(fields.phase)?"Battle":fields.phase)));
  if(minutes===null||fields.precision==="date"&&minutes<1440)return {...moved,ends_at:null};
  const first=Date.parse(fields.precision==="date"?start+"T00:00Z":start);
  if(!Number.isFinite(first))return {...moved,ends_at:null};
  const end=new Date(first+(fields.precision==="date"?Math.ceil(minutes/1440)*1440:minutes)*60000);
  if(!Number.isFinite(end.getTime())||end.getUTCFullYear()>2099)return {...moved,ends_at:null};
  return {...moved,ends_at:end.toISOString().slice(0,fields.precision==="date"?10:16)+(fields.precision==="minute"?"Z":"")};
}
export function legionPhases(phases:ScheduleFields[],two:boolean):ScheduleFields[]{
  const battle=phases.find(p=>isBattlePhase(p.phase));
  if(!battle)return phases;
  const prep=phases.filter(p=>!isBattlePhase(p.phase));
  const first={...battle,phase:"Legion 1"};
  return two?[...prep,first,{...first,phase:"Legion 2",precision:"date",starts_at:first.starts_at.slice(0,10),ends_at:null,confidence:"estimated"}]:[...prep,first];
}
const time=(p:ScheduleFields,value:string)=>Date.parse(p.precision==="date"?value+"T00:00Z":value);
function validateCycleDates(phases:ScheduleFields[]){
  const valid=(p:ScheduleFields,value:string)=>{
    const t=time(p,value);
    return Number.isFinite(t)&&new Date(t).getUTCFullYear()>=2000&&new Date(t).getUTCFullYear()<=2099&&
      (p.precision==="date"?new Date(t).toISOString().slice(0,10):new Date(t).toISOString().slice(0,16)+"Z")===value;
  };
  if(phases.some(p=>!valid(p,p.starts_at)||p.ends_at!==null&&(!valid(p,p.ends_at)||time(p,p.ends_at)<=time(p,p.starts_at))))throw Error("Enter valid phase dates.");
  if(phases.some((p,i)=>i>0&&!(isLegion(p.phase)&&isLegion(phases[i-1].phase))&&(time(p,p.starts_at)<=time(phases[i-1],phases[i-1].starts_at)||!!phases[i-1].ends_at&&time(p,p.starts_at)<time(phases[i-1],phases[i-1].ends_at!))))throw Error("Phases must be chronological and must not overlap.");
  const battles=phases.filter(p=>isLegion(p.phase));
  if(battles.length===2){
    if(battles[0].starts_at.slice(0,10)!==battles[1].starts_at.slice(0,10))throw Error("Legions must share the same battle date.");
    if(battles.every(p=>p.precision==="minute")&&battles[0].starts_at===battles[1].starts_at)throw Error("Choose distinct legion start times.");
    const prep=phases.find(p=>p.phase==="Matchmaking");
    if(prep?.ends_at&&battles.some(p=>time(p,p.starts_at)<time(prep,prep.ends_at!)))throw Error("Battle must follow matchmaking.");
  }
  const first=time(phases[0],phases[0].starts_at);
  if(phases.some(p=>time(p,p.ends_at??p.starts_at)-first>31*86400000))throw Error("Maximum cycle duration is 31 days.");
}
export function cycleOccurrences(kind:CycleKind,phases:ScheduleFields[],count:number,interval:number):ScheduleFields[][]{
  if(!Number.isInteger(count)||count<1||count>14||!Number.isInteger(interval)||interval<1||(count-1)*interval>366)throw Error("Choose up to 14 cycles within 366 days.");
  if(!phases.length)return [];
  validateCycleDates(phases);
  const first=time(phases[0],phases[0].starts_at);
  if(count>1&&Math.max(...phases.map(p=>time(p,p.ends_at??p.starts_at)))>=first+interval*86400000)throw Error("Repeat interval must exceed the cycle duration.");
  const cycles=Array.from({length:count},(_,i)=>phases.map((p):ScheduleFields=>{
    if(i===0)return p;
    const move=(v:string)=>addDays(v.slice(0,10),i*interval)+v.slice(10);
    if(kind!=="svs"&&isBattlePhase(p.phase))return {...p,starts_at:move(p.starts_at).slice(0,10),ends_at:null,precision:"date",confidence:"estimated"};
    return {...p,starts_at:move(p.starts_at),ends_at:p.ends_at?move(p.ends_at):null,confidence:"estimated"};
  }));
  for(const rows of cycles)validateCycleDates(rows);
  return cycles;
}

export type CycleSeries={id:string;interval_days:number;status:"active"|"finite"|"stopped"|"conflict";revision:number;sequence:number};
export function initialCycleCount(interval:number|null,rolling:boolean,count:number){
  return rolling&&interval!==null&&interval>=7&&interval<=60?1+Math.floor(60/interval):count;
}

export type CycleReconcilePlan={items:CalendarOccurrence[];protected_cycles:number;can_confirm:boolean;confirm_items:CalendarOccurrence[];series_revision:number|null;series_status:CycleSeries["status"]|null};
export type CycleReconcilePayload={action:"confirm"|"shift"|"stop"|"cadence";following:boolean;shift_days:number;interval_days?:number;revisions:Record<string,number>;series_revision:number|null};

export type CycleCadencePlan={items:CalendarOccurrence[];proposed:CalendarOccurrence[];anchor_items:CalendarOccurrence[];protected_cycles:number;interval_days:number;series_revision:number;next_start:string|null};
