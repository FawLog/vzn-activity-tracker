import {calendarEndInput,calendarEndValue,validCalendarEnd,type CalendarOccurrence} from "../lib/calendar";

export function CalendarEndField({value,precision,onChange}:{value:string|null;precision:CalendarOccurrence["precision"];onChange:(value:string|null)=>void}){
  const valid=validCalendarEnd(value,precision);
  return <label>{precision==="date"?"Last day (UTC, optional)":"Ends (UTC, optional)"}
    <input type={precision==="date"?"date":"text"} value={calendarEndInput(value,precision)}
      placeholder={precision==="minute"?"YYYY-MM-DD HH:mm":undefined}
      aria-invalid={!valid} onChange={e=>onChange(calendarEndValue(e.target.value,precision))}/>
    {precision==="date"?<small>Ends at 24:00 UTC on the selected day.</small>:<small>YYYY-MM-DD HH:mm · use 24:00 for the end of a day.</small>}
    {!valid&&<small role="alert">Enter a valid UTC end date and time.</small>}
  </label>;
}
