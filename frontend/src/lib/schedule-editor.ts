import type { CalendarOccurrence } from "./calendar";
export type ScheduleFields = Pick<CalendarOccurrence,"event_type"|"scope"|"alliance_id"|"state_id"|"starts_at"|"ends_at"|"precision"|"phase"|"confidence">;
export type ScheduleCreate = ScheduleFields & {request_key:string;interval_minutes:number|null;occurrence_count:number;reject_existing?:boolean;rolling?:boolean;bear_cycle_anchor?:string;bear_session_key?:string;repeat_months?:number;repeat_weekdays?:number[]};
export type ScheduleTemplateInput = Omit<ScheduleCreate,"request_key"|"repeat_months"|"repeat_weekdays"> & {repeat_months?:number|null;repeat_weekdays?:number[]|null};
export type ScheduleTemplate = {id:string;name:string;alliance_id:string;schedule:ScheduleTemplateInput};
export function templateFields(template:ScheduleTemplateInput,day:string):ScheduleFields{
  const {event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase}=template;
  const start=day+starts_at.slice(10);
  const old=Date.parse(precision==="date"?starts_at+"T00:00Z":starts_at);
  const next=Date.parse(precision==="date"?start+"T00:00Z":start);
  if(!Number.isFinite(old)||!Number.isFinite(next))throw Error("Choose a valid anchor date");
  let end:string|null=null;
  if(ends_at){
    const duration=Date.parse(precision==="date"?ends_at+"T00:00Z":ends_at)-old;
    const target=new Date(next+duration);
    if(!Number.isFinite(target.getTime())||target.getUTCFullYear()>2099)throw Error("Template duration exceeds supported dates");
    end=target.toISOString().slice(0,precision==="date"?10:16)+(precision==="minute"?"Z":"");
  }
  return {event_type,scope,alliance_id,state_id,starts_at:start,ends_at:end,precision,phase,confidence:"estimated"};
}
export type ScheduleUpdate = ScheduleFields & Pick<CalendarOccurrence,"revision"|"schedule_status">;
export type FutureChange = {action:"shift"|"cancel";shift_minutes:number;revisions:Record<string,number>} | {action:"edit";schedule:ScheduleUpdate;interval_minutes?:number;revisions:Record<string,number>};
export type FuturePreview = {items:CalendarOccurrence[];interval_minutes:number|null};
export function moveScheduleStart(fields:ScheduleFields,start:string):ScheduleFields{
  if(!start||!fields.starts_at||!fields.ends_at)return {...fields,starts_at:start};
  const old=Date.parse(fields.precision==="date"?fields.starts_at+"T00:00Z":fields.starts_at);
  const next=Date.parse(fields.precision==="date"?start+"T00:00Z":start);
  const end=Date.parse(fields.precision==="date"?fields.ends_at+"T00:00Z":fields.ends_at);
  if(![old,next,end].every(Number.isFinite))return {...fields,starts_at:start};
  const target=new Date(end+next-old);
  return {...fields,starts_at:start,ends_at:target.toISOString().slice(0,fields.precision==="date"?10:16)+(fields.precision==="minute"?"Z":"")};
}
export function futureEditDates(preview:FuturePreview,fields:ScheduleFields,hours:number):{id:string;start:string;end:string|null}[]{
  const first=preview.items[0];
  if(!first||!fields.starts_at||fields.precision!==first.precision)throw Error("Choose a start with the original precision.");
  const parse=(v:string)=>Date.parse(fields.precision==="date"?v+"T00:00Z":v);
  const start=parse(fields.starts_at),offset=start-parse(first.starts_at);
  const duration=fields.ends_at?parse(fields.ends_at)-start:null;
  if(!Number.isFinite(start)||!Number.isFinite(offset)||(duration!==null&&(!Number.isFinite(duration)||duration<=0||duration>31*86400000)))throw Error("Choose valid start and end dates.");
  const minutes=hours*60;
  if(preview.interval_minutes!==null&&(!Number.isInteger(minutes)||minutes<60||minutes>525600||(fields.precision==="date"&&minutes%1440)))throw Error("Choose a valid fixed repeat interval.");
  const format=(time:number)=>{
    const date=new Date(time);
    if(!Number.isFinite(date.getTime())||date.getUTCFullYear()<2000||date.getUTCFullYear()>2099)throw Error("Series edit exceeds supported dates.");
    return date.toISOString().slice(0,fields.precision==="date"?10:16)+(fields.precision==="minute"?"Z":"");
  };
  return preview.items.map(r=>{
    const time=preview.interval_minutes===null?parse(r.starts_at)+offset:start+(r.sequence-first.sequence)*minutes*60000;
    return {id:r.id,start:format(time),end:duration===null?null:format(time+duration)};
  });
}
export function utcInput(value:string,precision:ScheduleFields["precision"]):string {
  return precision==="date"?value.slice(0,10):value.slice(0,16);
}
export function serializeTime(value:string,precision:ScheduleFields["precision"]):string {
  return precision==="date"?value:value+"Z";
}
export function scheduleFields(row:CalendarOccurrence):ScheduleFields {
  const {event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence}=row;
  return {event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence};
}
export function recurrence(count:number,days:number){
  if(!Number.isInteger(count)||count<1||count>180)throw new Error("Choose 1–180 occurrences");
  if(count===1)return {occurrence_count:1,interval_minutes:null};
  if(!Number.isInteger(days)||days<1||(count-1)*days>366)throw new Error("Recurrence must fit within 366 days");
  return {occurrence_count:count,interval_minutes:days*1440};
}
export function futureChange(rows:CalendarOccurrence[],action:"shift"|"cancel",minutes:number):Extract<FutureChange,{action:"shift"|"cancel"}>{
  if(!rows.length)throw new Error("No eligible occurrences");
  if(action==="shift"&&(!Number.isInteger(minutes)||!minutes||Math.abs(minutes)>527040))throw new Error("Enter a nonzero shift within 366 days");
  if(action==="shift"&&rows.some(r=>r.precision==="date")&&minutes%1440!==0)throw new Error("Date-only events require whole-day shifts");
  return {action,shift_minutes:action==="cancel"?0:minutes,revisions:Object.fromEntries(rows.map(r=>[r.id,r.revision]))};
}

export function precisionChange(fields:ScheduleFields,precision:ScheduleFields["precision"]):ScheduleFields{
  if(fields.precision===precision)return fields;
  return {...fields,precision,starts_at:precision==="date"?fields.starts_at.slice(0,10):"",ends_at:null};
}
export function shiftedStart(row:CalendarOccurrence,minutes:number):string{
  futureChange([row],"shift",minutes);
  const target=new Date(Date.parse(row.precision==="date"?row.starts_at+"T00:00Z":row.starts_at)+minutes*60000);
  if(!Number.isFinite(target.getTime())||target.getUTCFullYear()<2000||target.getUTCFullYear()>2099)throw Error("Shift outside supported dates");
  return target.toISOString().slice(0,row.precision==="date"?10:16)+(row.precision==="minute"?"Z":"");
}

export function bearCycleDates(fields:ScheduleFields,anchor:string,key:string,count:number,minutes:number,mode:string):string[]{
  if(fields.event_type!=="bear_trap"||fields.scope!=="alliance"||fields.precision!=="minute"||mode!=="fixed"||!Number.isInteger(minutes)||minutes<1440||minutes>10080||count<2)throw Error("Bear grouping requires timed alliance traps and a fixed 1–7 day repeat interval.");
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/.test(anchor)||!/^trap_(?:[1-9]|[12][0-9]|30)$/.test(key))throw Error("Choose the shared UTC cycle anchor and unique trap identity.");
  const first=Date.parse(anchor),start=Date.parse(fields.starts_at);
  if(!Number.isFinite(first)||!Number.isFinite(start)||new Date(first).toISOString().slice(0,16)+"Z"!==anchor||Number(anchor.slice(0,4))<2000||Number(anchor.slice(0,4))>2099||start<first||start-first>=minutes*60000)throw Error("First trap must fall within the first shared Bear cycle.");
  return Array.from({length:count},(_,i)=>new Date(first+i*minutes*60000).toISOString().slice(0,10));
}

export type EditScope="single"|"all"|"following";
export type ScopedEditInfo={recurring:boolean;interval_minutes:number|null;protected_count:number;linked:boolean;following_count:number};
export type ScopedEditPayload={scope:EditScope;schedule:ScheduleUpdate;interval_minutes?:number;preview:boolean;token?:string};
export type ScopedEditResult=ScopedEditInfo&{items:CalendarOccurrence[];before:CalendarOccurrence[];token:string};
