import type { GameEventSummary, GameRun } from "./game-event-catalog";
import type { ScheduleFields } from "./schedule-editor";

const DAY=1440;
const units={minutes:1,hours:60,days:DAY,weeks:7*DAY};
export function fixedGameInterval(event:GameEventSummary|undefined):number|null{
  const repeat=event?.schedule?.repeat;
  // A cooldown is not an alliance commitment. A monthly rule is not 30 days.
  if(!event||event.id==="bear-hunt"||repeat?.kind!=="every"||repeat.unit==="months")return null;
  const minutes=repeat.every*units[repeat.unit];
  return Number.isInteger(minutes)&&minutes>=60&&minutes<=525600?minutes:null;
}
export function intervalPayload(count:number,minutes:number,precision:ScheduleFields["precision"]){
  if(!Number.isInteger(count)||count<1||count>180)throw Error("Choose 1–180 occurrences");
  if(count===1)return {occurrence_count:1,interval_minutes:null};
  if(!Number.isInteger(minutes)||minutes<60||minutes>525600||(count-1)*minutes>366*DAY)throw Error("Repeat interval must fit within 366 days");
  if(precision==="date"&&minutes%DAY)throw Error("Date-only schedules require whole-day intervals");
  return {occurrence_count:count,interval_minutes:minutes};
}
function parse(value:string,precision:ScheduleFields["precision"]){
  const pattern=precision==="date"?/^\d{4}-\d{2}-\d{2}$/:/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/;
  if(!pattern.test(value))throw Error("Enter a valid UTC start");
  const millis=Date.parse(precision==="date"?value+"T00:00Z":value);
  if(!Number.isFinite(millis)||format(millis,precision)!==value)throw Error("Enter a valid UTC date");
  return millis;
}
function format(ms:number,precision:ScheduleFields["precision"]){
  const d=new Date(ms);
  if(!Number.isFinite(d.getTime())||d.getUTCFullYear()<2000||d.getUTCFullYear()>2099)throw Error("Date outside supported range");
  return precision==="date"?d.toISOString().slice(0,10):d.toISOString().slice(0,16)+"Z";
}
export function forecastRows(fields:ScheduleFields,count:number,minutes:number){
  const payload=intervalPayload(count,minutes,fields.precision);
  const start=parse(fields.starts_at,fields.precision);
  const end=fields.ends_at?parse(fields.ends_at,fields.precision):null;
  if(end!==null&&(end<=start||end-start>31*DAY*60000))throw Error("End must follow start, with duration at most 31 days");
  return Array.from({length:count},(_,i)=>{
    const offset=i*(payload.interval_minutes??0)*60000;
    return {start:format(start+offset,fields.precision),end:end===null?null:format(end+offset,fields.precision),confidence:i===0?fields.confidence:"estimated"};
  });
}
export function runForType(event:GameEventSummary|undefined,type:string,phase=""):GameRun|undefined{
  const runs=event?.schedule?.runs??[];
  if(type==="svs_matchmaking")return runs.find(r=>r.label==="Matchmaking");
  if(type==="svs_triage")return runs.find(r=>r.label==="Field Triage");
  if(type==="svs_preparation")return runs.find(r=>r.label==="Preparation");
  if(type==="svs_battle"||type==="canyon"||type==="foundry")return runs.find(r=>r.label==="Battle");
  if(event?.id==="hall-of-chief")return runs.find(r=>r.label?.toLowerCase()===phase.trim().toLowerCase());
  if(event?.id==="icefire-warhymn-league"&&runs.length===2&&runs[0].label==="Preview"&&runs[1].label==="Competition"&&runs[0].length===24&&runs[0].unit==="hours"&&runs[1].length===6&&runs[1].unit==="days")return {length:7,unit:"days",startWeekday:"sunday"};
  if(runs.length>1&&["frostfire-mine","crazy-joe"].includes(event?.id??"")&&runs.every(r=>r.length===runs[0].length&&r.unit===runs[0].unit))return {length:runs[0].length,unit:runs[0].unit};
  return runs.length===1?runs[0]:undefined;
}
// Only a structured run (not descriptive prose or a repeat cooldown) can supply a duration.
export function runMinutes(run:GameRun|undefined):number|null{
  if(!run)return null;
  const n=run.length*units[run.unit];
  return Number.isInteger(n)&&n>0&&n<=31*DAY?n:null;
}
export function referenceDuration(event:GameEventSummary|undefined,type:string,phase=""):number|null{
  const n=runMinutes(runForType(event,type,phase));
  if(n===null)return null;
  // Source daily-stage metadata explicitly extends these reset-based final days.
  if(type==="svs_preparation"&&n===5*DAY)return n+600;
  if(type==="alliance_showdown"&&n===6*DAY)return n+720;
  return n;
}
export function referenceEnd(event:GameEventSummary|undefined,fields:ScheduleFields):string|null{
  const n=referenceDuration(event,fields.event_type,fields.phase);
  if(n===null||!fields.starts_at)return null;
  // A date-only short battle has no known start time. Do not invent one.
  if(fields.precision==="date"&&n<DAY)return null;
  try{
    const start=parse(fields.starts_at,fields.precision);
    // For date precision, cover every occupied UTC date; exact end requires UTC time.
    return format(start+(fields.precision==="date"?Math.ceil(n/DAY)*DAY:n)*60000,fields.precision);
  }catch{return null;}
}
export function sourceRunWarning(event:GameEventSummary|undefined,type:string,fields:ScheduleFields):string[]{
  const result:string[]=[];
  if(!event)return result;
  const run=runForType(event,type,fields.phase);
  const date=new Date(fields.starts_at.slice(0,10)+"T00:00Z");
  if(run?.startWeekday&&!Number.isNaN(date.getTime())){
    const weekday=["sunday","monday","tuesday","wednesday","thursday","friday","saturday"][date.getUTCDay()];
    if(weekday!==run.startWeekday.toLowerCase())result.push("Anchor weekday differs from the game reference ("+run.startWeekday+").");
  }
  if(run?.startTimeUtc&&fields.precision==="minute"&&fields.starts_at.slice(11,16)!==run.startTimeUtc)result.push("Anchor time differs from the game reference ("+run.startTimeUtc+" UTC).");
  if(type==="svs_preparation")result.push("Preparation includes the extended fifth stage; verify the in-game end.");
  if(type==="svs_triage")result.push("Field Triage end is a community estimate; verify the in-game timer.");
  if(type==="alliance_showdown")result.push("The last stage can extend into Sunday. Confirm the end manually.");
  if(type==="castle_battle")result.push("Castle weeks can overlap SvS; verify the local rotation.");
  if(type==="canyon"||type==="foundry")result.push("This schedules a battle only; use the full event editor for a complete cycle.");
  if(event.id==="bear-hunt")result.push("47.5 hours is a cooldown, not the alliance's chosen schedule.");
  if(event.scheduleDependency)result.push(event.scheduleOverride?.note??"Verify the parent event and local timing.");
  if(event.id==="frostfire-mine")result.push("Choose a local time slot: "+(event.schedule?.runs??[]).map(r=>r.startTimeUtc).filter(Boolean).join(", ")+" UTC. The schedule represents one selected slot.");
  if(event.id==="hall-of-chief"&&!run)result.push("Choose Season 1 or Season 2 to determine duration.");
  if(event.id==="alliance-mobilization")result.push("The monthly/early-state rotation needs a locally verified pattern; use manual scheduling.");
  return result;
}
export function stateAge(startDate:string,anchor:string):number{
  const first=parse(startDate,"date"),last=parse(anchor.slice(0,10),"date");
  if(last<first)throw Error("Anchor precedes the state start date");
  return (last-first)/(DAY*60000);
}

export type RepeatMode="fixed"|"months"|"weekdays";
export function advancedPlan(fields:ScheduleFields,count:number,minutes:number,mode:RepeatMode,months:number,weekdays:number[]){
  if(mode==="fixed"||count===1)return {payload:intervalPayload(count,minutes,fields.precision),rows:forecastRows(fields,count,minutes)};
  if(!Number.isInteger(count)||count<2||count>180)throw Error("Choose 2–180 occurrences");
  const anchor=parse(fields.starts_at,fields.precision),end=fields.ends_at?parse(fields.ends_at,fields.precision):null;
  if(end!==null&&(end<=anchor||end-anchor>31*DAY*60000))throw Error("End must follow start, with duration at most 31 days");
  const a=new Date(anchor),offsets=[0],dayMs=86400000;
  if(mode==="months"){
    if(!Number.isInteger(months)||months<1||months>12)throw Error("Choose 1–12 calendar months");
    for(let i=1;i<count;i++){
      const target=new Date(anchor);
      target.setUTCDate(1);target.setUTCMonth(a.getUTCMonth()+i*months);
      const last=new Date(Date.UTC(target.getUTCFullYear(),target.getUTCMonth()+1,0)).getUTCDate();
      target.setUTCDate(Math.min(a.getUTCDate(),last));
      offsets.push(target.getTime()-anchor);
    }
  }else{
    const first=(a.getUTCDay()+6)%7;
    if(!weekdays.includes(first)||weekdays.some(d=>!Number.isInteger(d)||d<0||d>6)||new Set(weekdays).size!==weekdays.length)throw Error("Anchor must match a selected weekday");
    for(let day=1;day<=366&&offsets.length<count;day++)if(weekdays.includes((first+day)%7))offsets.push(day*dayMs);
  }
  if(offsets.length!==count||offsets[offsets.length-1]>366*dayMs)throw Error("Maximum recurrence horizon is 366 days");
  const payload={occurrence_count:count,interval_minutes:null,...(mode==="months"?{repeat_months:months}:{repeat_weekdays:[...weekdays].sort((a,b)=>a-b)})};
  return {payload,rows:offsets.map((offset,i)=>({start:format(anchor+offset,fields.precision),end:end===null?null:format(end+offset,fields.precision),confidence:i===0?fields.confidence:"estimated"}))};
}

// Calendar-month rules are anchored estimates, not fixed 30-day intervals.
// State-dependent rotations require explicit selection of the reference rule.
export function referenceRepeat(event:GameEventSummary|undefined,explicit=false):{mode:RepeatMode;count:number;days:number;months:number;weekdays:number[]}{
  const fallback={mode:"fixed" as const,count:1,days:2,months:1,weekdays:[]};
  const fixed=fixedGameInterval(event);
  if(fixed!==null&&fixed%1440===0)return {...fallback,count:Math.min(4,1+Math.floor(366*1440/fixed)),days:fixed/1440};
  const rule=event?.schedule?.repeat;
  if(rule?.kind==="every"&&rule.unit==="months"&&(explicit||!["alliance-mobilization","king-of-icefield","brothers-in-arms"].includes(event?.id??""))){
    if(!Number.isInteger(rule.every)||rule.every<1||rule.every>12)return fallback;
    return {...fallback,mode:"months",count:Math.min(4,1+Math.floor(12/rule.every)),months:rule.every};
  }
  if(rule?.kind==="weekly"){
    const weekdays=rule.weekdays.map(d=>["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].indexOf(d.toLowerCase()));
    if(weekdays.length&&weekdays.every(d=>d>=0))return {...fallback,mode:"weekdays",count:4,weekdays};
  }
  return fallback;
}
