import { addDays, occursOn, type CalendarOccurrence } from "./calendar";
import { gameEventForCalendar, type GameStage } from "./game-event-catalog";

export interface CalendarStage {
  id:string;
  name:string;
  start:string;
  end:string;
  note?:string;
}
export interface StagePlan {
  stages:CalendarStage[];
  warning?:string;
}

// Reference projections never change the scheduled parent, its confidence or its end.
// Daily stages are assigned only where the reference identifies actual sequential days.
export function stagePlan(row:CalendarOccurrence):StagePlan{
  const reference=gameEventForCalendar(row.event_type);
  const none:StagePlan={stages:[]};
  if(!reference||row.schedule_status==="cancelled")return none;
  if(row.event_type==="svs_battle")return none;
  if(row.event_type==="canyon")return none; // Battle is a separate occurrence, never assume a whole Canyon cycle.
  if(!row.ends_at)return {stages:[],warning:reference.stages.length?"Set an explicit event end to project daily stages.":undefined};
  if(row.precision==="minute"&&!row.starts_at.endsWith("T00:00Z"))return {stages:[],warning:reference.stages.length?"Daily stages require a verified UTC reset anchor (00:00).":undefined};
  let source:GameStage[]=reference.stages;
  if(row.event_type==="svs_preparation")source=source.filter(s=>/^[1-5]$/.test(s.id));
  if(reference.id==="hall-of-chief"){
    const season=row.phase.trim().toLowerCase();
    if(season!=="season 1"&&season!=="season 2")return {stages:[],warning:"Select the Hall of Chief season explicitly in Phase (Season 1 or Season 2)."};
    const prefix=season==="season 1"?"s1-":"s2-";
    source=source.filter(s=>s.id.startsWith(prefix)).map(s=>({...s,id:s.id.slice(3)}));
  }
  if(reference.hasVariants&&reference.id!=="hall-of-chief"&&row.event_type!=="svs_preparation")return {stages:[],warning:"Event variants need verification; reference stages are listed below without assigned dates."};
  if(!source.length)return none;
  if(source.some(s=>!/^\d+(?:-\d+)?$/.test(s.id)))return {stages:[],warning:"Reference stage timing is ambiguous; no dates assigned."};
  const base=row.starts_at.slice(0,10),stages:CalendarStage[]=[];
  const point=(day:number)=>addDays(base,day)+(row.precision==="minute"?"T00:00Z":"");
  for(const s of source){
    const [first,last=first]=s.id.split("-").map(Number);
    if(first<1||last<first||last>31)continue;
    let start=point(first-1),end=point(last);
    // Source explicitly gives the extended final stage of these two events.
    if(row.precision==="minute"&&row.event_type==="svs_preparation"&&first===5)end=addDays(base,5)+"T10:00Z";
    if(row.precision==="minute"&&row.event_type==="alliance_showdown"&&first===6)end=addDays(base,6)+"T12:00Z";
    if(start>=row.ends_at)continue;
    if(end>row.ends_at)end=row.ends_at;
    stages.push({id:s.id,name:s.name??"Stage "+s.id,start,end,note:s.note});
  }
  const warning=row.event_type==="svs_preparation"?"Reference duration conflicts (5 days, 6 days, and extended Day 5). Stage dates are estimates clipped to the saved event end.":row.event_type==="alliance_showdown"?"Final stage can extend into Sunday. Stage dates are estimates clipped to the saved event end.":"Reference stages are estimates; verify the event version and reset.";
  return {stages,warning};
}
export function stagesOn(row:CalendarOccurrence,day:string):CalendarStage[]{
  if(!occursOn(row,day))return [];
  return stagePlan(row).stages.filter(s=>occursOn({...row,starts_at:s.start,ends_at:s.end},day));
}
export function eventDay(row:CalendarOccurrence,day:string):string|null{
  if(!row.ends_at||!occursOn(row,day))return null;
  const start=Date.parse(row.starts_at.slice(0,10)+"T00:00Z");
  const endDay=row.ends_at.slice(0,10);
  const exclusive=row.precision==="date"||row.ends_at.endsWith("T00:00Z");
  const total=(Date.parse(endDay+"T00:00Z")-start)/86400000+(exclusive?0:1);
  const index=(Date.parse(day+"T00:00Z")-start)/86400000+1;
  return total>1?"Day "+index+" of "+total:null;
}
