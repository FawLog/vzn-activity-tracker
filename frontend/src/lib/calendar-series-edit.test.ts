import {describe,expect,it} from "vitest";
import {futureEditDates,moveScheduleStart,type ScheduleFields,type FuturePreview} from "./schedule-editor";
import type {CalendarOccurrence} from "./calendar";
const fields:ScheduleFields={event_type:"bear_trap",scope:"alliance",alliance_id:"a",state_id:"1001",precision:"minute",starts_at:"2090-06-01T15:00Z",ends_at:"2090-06-01T15:30Z",phase:"",confidence:"confirmed"};
const row=(id:string,sequence:number,starts_at:string):CalendarOccurrence=>({...fields,id,group_id:"g",series_id:"s",sequence,starts_at,ends_at:null,source:"recurrence",revision:1,schedule_status:"scheduled"});
describe("recurring edit preview",()=>{
  it("preserves duration and uses sequence gaps rather than moving each row by the selected exception's offset",()=>{
    const updated=moveScheduleStart(fields,"2090-06-01T17:00Z");
    expect(updated.ends_at).toBe("2090-06-01T17:30Z");
    const preview:FuturePreview={interval_minutes:2880,items:[row("a",2,"2090-06-01T15:00Z"),row("b",4,"2090-06-05T15:00Z")]};
    expect(futureEditDates(preview,updated,47.5)).toEqual([{id:"a",start:"2090-06-01T17:00Z",end:"2090-06-01T17:30Z"},{id:"b",start:"2090-06-05T16:00Z",end:"2090-06-05T16:30Z"}]);
  });
});
