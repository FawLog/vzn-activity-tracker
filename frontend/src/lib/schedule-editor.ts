import type { CalendarOccurrence } from "./calendar";
export type ScheduleFields = Pick<CalendarOccurrence,"event_type"|"scope"|"alliance_id"|"state_id"|"starts_at"|"ends_at"|"precision"|"phase"|"confidence">;
export type ScheduleCreate = ScheduleFields & {request_key:string;interval_minutes:number|null;occurrence_count:number;reject_existing?:boolean;repeat_months?:number;repeat_weekdays?:number[]};
export type ScheduleUpdate = ScheduleFields & Pick<CalendarOccurrence,"revision"|"schedule_status">;
export type FutureChange = {action:"shift"|"cancel";shift_minutes:number;revisions:Record<string,number>};
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
export function futureChange(rows:CalendarOccurrence[],action:FutureChange["action"],minutes:number):FutureChange{
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
