export type CalendarView = "Agenda" | "Week" | "Month";
export type ReviewFlag="reviewed"|"partial"|"not_recorded"|"not_applicable";
export interface CalendarReview {
  publication:"draft"|"published";
  scope:"session"|"event";
  session_count:number;
  roster:ReviewFlag;
  registration:ReviewFlag;
  attendance:ReviewFlag;
  results:ReviewFlag;
  final_attendance_review:boolean|null;
}
export interface CalendarOccurrence {
  follow_rule_id?:string;
  follow_parent_id?:string;
  follow_parent_label?:string;
  follow_active?:boolean;
  review?:CalendarReview;
  rolling_status?:"active"|"stopped"|"conflict";
  entry_cycle_date?:string|null;
  entry_session_key?:string|null;
  id: string;
  group_id: string;
  series_id: string | null;
  cycle_id?: string | null;
  sequence: number;
  event_type: string;
  scope: "alliance" | "state";
  alliance_id: string | null;
  state_id: string;
  starts_at: string;
  ends_at: string | null;
  precision: "date" | "minute";
  phase: string;
  confidence: "confirmed" | "estimated";
  schedule_status: "scheduled" | "cancelled";
  source: "manual" | "recurrence";
  revision: number;
}

export const utcDay = (date = new Date()) => date.toISOString().slice(0,10);
export function addDays(day:string, count:number):string {
  const d=new Date(day+"T00:00:00Z");
  d.setUTCDate(d.getUTCDate()+count);
  return utcDay(d);
}
export function weekStart(day:string):string {
  const weekday=new Date(day+"T00:00:00Z").getUTCDay();
  return addDays(day,-((weekday+6)%7));
}
export function monthStart(day:string):string {return day.slice(0,7)+"-01";}
export function addMonths(day:string,count:number):string {
  const date=new Date(monthStart(day)+"T00:00:00Z");
  date.setUTCMonth(date.getUTCMonth()+count);
  return utcDay(date);
}
export function calendarRange(day:string,view:CalendarView) {
  const start=view==="Month"?weekStart(monthStart(day)):weekStart(day);
  const end=view==="Month"?addDays(start,42):addDays(start,7);
  return {start,end,days:Array.from({length:view==="Month"?42:7},(_,i)=>addDays(start,i))};
}
export function moveCalendar(day:string,view:CalendarView,direction:number):string {
  return view==="Month"?addMonths(day,direction):addDays(day,direction*7);
}
export function occursOn(row:CalendarOccurrence,day:string):boolean {
  const next=addDays(day,1);
  return row.starts_at.slice(0,10)<next && (row.starts_at.slice(0,10)>=day ||
    (!!row.ends_at && row.ends_at>(row.precision==="date"?day:day+"T00:00Z")));
}
export function calendarTime(row:CalendarOccurrence,day:string):string {
  if(row.precision==="date")return "Time not set";
  if(row.starts_at.slice(0,10)<day)return "Continues";
  return row.starts_at.slice(11,16)+" UTC";
}


// End timestamps are exclusive internally. Only the end presentation uses the
// game's 24:00 convention; starts, comparisons, recurrence and API payloads do not.
function canonicalEnd(value:string,precision:CalendarOccurrence["precision"]):boolean{
  const pattern=precision==="date"?/^\d{4}-\d{2}-\d{2}$/:/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/;
  if(!pattern.test(value))return false;
  const d=new Date(precision==="date"?value+"T00:00Z":value);
  return Number.isFinite(d.getTime())&&(precision==="date"?d.toISOString().slice(0,10):d.toISOString().slice(0,16)+"Z")===value;
}
export function validCalendarEnd(value:string|null,precision:CalendarOccurrence["precision"]):boolean{
  return value===null||canonicalEnd(value,precision)&&Number(value.slice(0,4))>=2000&&Number(value.slice(0,4))<=2099;
}
export function calendarEndInput(value:string|null,precision:CalendarOccurrence["precision"]):string{
  if(!value)return "";
  if(!canonicalEnd(value,precision))return value;
  if(precision==="date")return addDays(value,-1);
  if(value.endsWith("T00:00Z"))return addDays(value.slice(0,10),-1)+" 24:00";
  return value.slice(0,10)+" "+value.slice(11,16);
}
export function calendarEndValue(input:string,precision:CalendarOccurrence["precision"]):string|null{
  if(!input)return null;
  if(precision==="date")return canonicalEnd(input,"date")?addDays(input,1):input;
  const match=/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})$/.exec(input);
  if(!match||!canonicalEnd(match[1],"date"))return input;
  const value=match[2]==="24:00"?addDays(match[1],1)+"T00:00Z":match[1]+"T"+match[2]+"Z";
  return canonicalEnd(value,"minute")?value:input;
}
export function calendarEndLabel(value:string|null,precision:CalendarOccurrence["precision"]):string{
  if(!value)return "End time not set";
  if(!canonicalEnd(value,precision))return value;
  const display=calendarEndInput(value,precision);
  return display+(precision==="date"?" 24:00 UTC":" UTC");
}
