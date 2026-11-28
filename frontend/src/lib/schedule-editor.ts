import type { CalendarOccurrence } from "./calendar";
export type ScheduleFields = Pick<CalendarOccurrence,"event_type"|"scope"|"alliance_id"|"state_id"|"starts_at"|"ends_at"|"precision"|"phase"|"confidence">;
export type ScheduleCreate = ScheduleFields & {request_key:string;interval_minutes:number|null;occurrence_count:number};
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
