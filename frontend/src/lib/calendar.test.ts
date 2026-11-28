import { describe, expect, it } from "vitest";
import { addDays, calendarRange, moveCalendar, occursOn, calendarTime,calendarEndInput,calendarEndValue,calendarEndLabel,validCalendarEnd,type CalendarOccurrence } from "./calendar";
const row:CalendarOccurrence={id:"a",group_id:"g",series_id:null,sequence:0,event_type:"foundry",scope:"alliance",alliance_id:"a",state_id:"1001",starts_at:"2028-02-29T23:30Z",ends_at:"2028-03-01T00:00Z",precision:"minute",phase:"Legion 1",confidence:"confirmed",schedule_status:"scheduled",source:"manual",revision:1};
describe("UTC calendar",()=>{
  it("uses Monday and exclusive end across a year",()=>{
    const r=calendarRange("2027-01-01","Week");
    expect(r.start).toBe("2026-12-28");
    expect(r.end).toBe("2027-01-04");
    expect(r.days).toHaveLength(7);
  });
  it("keeps month navigation stable and includes leap day",()=>{
    expect(addDays("2028-02-28",1)).toBe("2028-02-29");
    expect(moveCalendar("2028-01-31","Month",1)).toBe("2028-02-01");
    const r=calendarRange("2028-02-29","Month");
    expect(r.days).toHaveLength(42);
    expect(r.days).toContain("2028-02-29");
  });
  it("does not show an event on its exclusive end day",()=>{
    expect(occursOn(row,"2028-02-29")).toBe(true);
    expect(occursOn(row,"2028-03-01")).toBe(false);
    expect(occursOn({...row,ends_at:"2028-03-01T00:30Z"},"2028-03-01")).toBe(true);
    expect(calendarTime(row,"2028-02-29")).toBe("23:30 UTC");
  });
  it("does not invent a midnight start for date-only events",()=>{
    const dateOnly:CalendarOccurrence={...row,precision:"date",starts_at:"2028-02-29",ends_at:"2028-03-02"};
    expect(occursOn(dateOnly,"2028-03-01")).toBe(true);
    expect(occursOn(dateOnly,"2028-03-02")).toBe(false);
    expect(calendarTime(dateOnly,"2028-02-29")).toBe("Time not set");
  });
});

import { futureChange, recurrence, scheduleFields, serializeTime } from "./schedule-editor";
describe("schedule editor payloads",()=>{
  it("preserves date-only precision and explicit UTC time",()=>{
    expect(serializeTime("2028-02-29","date")).toBe("2028-02-29");
    expect(serializeTime("2028-02-29T23:30","minute")).toBe(row.starts_at);
    expect(scheduleFields(row)).not.toHaveProperty("revision");
  });
  it("bounds recurring schedules",()=>{
    expect(recurrence(1,2)).toEqual({occurrence_count:1,interval_minutes:null});
    expect(recurrence(3,2)).toEqual({occurrence_count:3,interval_minutes:2880});
    expect(()=>recurrence(180,3)).toThrow();
  });
  it("passes reviewed revisions and restricts date-only shifts",()=>{
    const dateRow:CalendarOccurrence={...row,precision:"date",starts_at:"2028-02-29",ends_at:null};
    expect(futureChange([dateRow],"cancel",60)).toEqual({action:"cancel",shift_minutes:0,revisions:{a:1}});
    expect(()=>futureChange([dateRow],"shift",60)).toThrow();
    expect(futureChange([dateRow],"shift",-1440).shift_minutes).toBe(-1440);
  });
});

import {precisionChange,shiftedStart} from "./schedule-editor";
describe("calendar verification regressions",()=>{
  it("requires explicit time rather than inserting midnight",()=>{
    const fields=scheduleFields({...row,precision:"date",starts_at:"2028-02-29",ends_at:null});
    expect(precisionChange(fields,"minute").starts_at).toBe("");
  });
  it("rejects unsafe shifts before rendering a preview",()=>{
    expect(()=>shiftedStart(row,1e15)).toThrow();
    expect(()=>shiftedStart(row,0)).toThrow();
    expect(shiftedStart(row,60)).toBe("2028-03-01T00:30Z");
  });
});


describe("game-style end of day (display only)",()=>{
 it("round-trips 24:00 to the exclusive midnight across month, leap day and year",()=>{
   for(const [stored,display] of [["2026-11-30T00:00Z","2026-11-29 24:00"],["2028-03-01T00:00Z","2028-02-29 24:00"],["2027-01-01T00:00Z","2026-12-31 24:00"]]){
     expect(calendarEndInput(stored,"minute")).toBe(display);
     expect(calendarEndValue(display,"minute")).toBe(stored);
     expect(calendarEndLabel(stored,"minute")).toBe(display+" UTC");
     expect(occursOn({...row,starts_at:display.slice(0,10)+"T15:00Z",ends_at:stored},stored.slice(0,10))).toBe(false);
   }
 });
 it("keeps precise non-midnight ends and unknown ends unchanged",()=>{
   expect(calendarEndInput("2026-11-30T10:00Z","minute")).toBe("2026-11-30 10:00");
   expect(calendarEndValue("2026-11-30 10:00","minute")).toBe("2026-11-30T10:00Z");
   expect(calendarEndInput("2026-11-30","date")).toBe("2026-11-29");
   expect(calendarEndValue("2026-11-29","date")).toBe("2026-11-30");
   expect(calendarEndLabel("2026-11-30","date")).toBe("2026-11-29 24:00 UTC");
   expect(calendarEndValue("","minute")).toBeNull();
   expect(validCalendarEnd(null,"minute")).toBe(true);
   for(const input of ["2026-11-29 24:01","2026-02-30 24:00","2026-11-29 2","2099-12-31 24:00"]){
     expect(validCalendarEnd(calendarEndValue(input,"minute"),"minute")).toBe(false);
   }
 });
});
