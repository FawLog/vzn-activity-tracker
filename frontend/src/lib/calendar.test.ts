import { describe, expect, it } from "vitest";
import { addDays, agendaGroups, agendaTime, calendarRange, moveCalendar, occursOn, calendarTime,calendarEndInput,calendarEndValue,calendarEndLabel,validCalendarEnd,type CalendarOccurrence } from "./calendar";
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

describe("upcoming agenda",()=>{
  const now=new Date("2026-11-28T17:36:20Z");
  const timed=(id:string,start:string,end:string|null=null):CalendarOccurrence=>({...row,id,starts_at:start,ends_at:end});
  const allDay=(id:string,start:string,end:string|null=null):CalendarOccurrence=>({...row,id,starts_at:start,ends_at:end,precision:"date"});
  it("uses a rolling 30-day window, not the current week, and cannot page into history",()=>{
    expect(calendarRange("2026-11-23","Agenda",now)).toMatchObject({start:"2026-11-28",end:"2026-12-28"});
    expect(moveCalendar("2026-11-28","Agenda",-1,now)).toBe("2026-11-28");
    expect(moveCalendar("2026-11-28","Agenda",1,now)).toBe("2026-12-28");
    expect(moveCalendar("2026-12-28","Agenda",-1,now)).toBe("2026-11-28");
  });
  it("keeps ongoing and upcoming records only, with no empty days or repeated multi-day cards",()=>{
    const active=allDay("ongoing","2026-11-25","2026-11-30");
    const groups=agendaGroups([
      timed("late","2026-11-28T19:30Z"),allDay("ended","2026-11-25","2026-11-28"),
      timed("midnight-trap","2026-11-28T00:00Z","2026-11-28T00:30Z"),
      timed("finished-at-this-minute","2026-11-28T17:00Z","2026-11-28T17:36Z"),
      timed("active-timed","2026-11-28T17:00Z","2026-11-28T18:00Z"),
      timed("point-past","2026-11-28T16:00Z"),
      active,active,allDay("unknown-today","2026-11-28"),
      timed("early","2026-11-28T19:00Z"),allDay("later","2026-12-10","2026-12-13")
    ],"2026-11-28","2026-12-28",now);
    expect(groups.map(g=>[g.day,g.ongoing,g.items.map(r=>r.id)])).toEqual([
      ["2026-11-28",true,["active-timed","ongoing"]],
      ["2026-11-28",false,["unknown-today","early","late"]],
      ["2026-12-10",false,["later"]]
    ]);
  });
  it("does not repeat an earlier multi-day event in the next future page",()=>{
    const earlier=allDay("overlap","2026-12-27","2026-12-30");
    const next=allDay("next","2026-12-29");
    expect(agendaGroups([earlier,next],"2026-12-28","2027-01-27",now).flatMap(g=>g.items.map(r=>r.id))).toEqual(["next"]);
  });
  it("shows meaningful time only and preserves midnight end-of-day convention",()=>{
    expect(agendaTime(allDay("mia","2026-11-28"),"2026-11-28",false)).toBeNull();
    expect(agendaTime(allDay("one-day","2026-11-28","2026-11-29"),"2026-11-28",false)).toBeNull();
    expect(agendaTime(allDay("multi","2026-11-25","2026-11-30"),"2026-11-28",true)).toBe("Ends Nov 29");
    expect(agendaTime(timed("trap","2026-11-28T19:00Z","2026-11-28T19:30Z"),"2026-11-28",false)).toBe("19:00 UTC · Ends 19:30 UTC");
    expect(agendaTime(timed("midnight","2026-11-28T23:30Z","2026-11-29T00:00Z"),"2026-11-28",false)).toBe("23:30 UTC · Ends 24:00 UTC");
  });
  it("removes finished events as the clock advances without changing the schedule",()=>{
    const event=timed("trap","2026-11-28T19:00Z","2026-11-28T19:30Z");
    expect(agendaGroups([event],"2026-11-28","2026-12-28",new Date("2026-11-28T19:05Z"))[0].ongoing).toBe(true);
    expect(agendaGroups([event],"2026-11-28","2026-12-28",new Date("2026-11-28T19:30Z"))).toEqual([]);
  });
});
