import {describe,expect,it} from "vitest";
import type {CalendarOccurrence} from "./calendar";
import {upcomingEvents,upcomingTiming,upcomingCalendarUrl} from "./upcoming-events";
const now=Date.parse("2028-02-29T15:00Z");
const row:CalendarOccurrence={id:"a",group_id:"g",series_id:null,sequence:0,event_type:"foundry",scope:"alliance",alliance_id:"a",state_id:"1001",starts_at:"2028-02-29T16:30Z",ends_at:null,precision:"minute",phase:"Legion 1",confidence:"confirmed",schedule_status:"scheduled",source:"manual",revision:1};
describe("upcoming schedule",()=>{
  it("filters group, alliance, state, cancelled and elapsed entries",()=>{
    const rows=[row,{...row,id:"past",starts_at:"2028-02-29T14:00Z"},{...row,id:"other",alliance_id:"b"},{...row,id:"group",group_id:"x"},{...row,id:"cancel",schedule_status:"cancelled" as const},{...row,id:"state",scope:"state" as const,alliance_id:null},{...row,id:"otherstate",scope:"state" as const,alliance_id:null,state_id:"1002"},{...row,id:"end",starts_at:"2028-03-07T00:00Z"}];
    expect(upcomingEvents(rows,now,"g",new Set(["a"]),new Set(["1001"])).map(r=>r.id)).toEqual(["a","state"]);
  });
  it("keeps continuing schedules and never invents midnight for date-only entries",()=>{
    const continuing={...row,starts_at:"2028-02-28T15:00Z",ends_at:"2028-03-01T10:00Z"};
    const dateOnly:CalendarOccurrence={...row,id:"d",precision:"date",starts_at:"2028-02-29"};
    expect(upcomingEvents([row,continuing,dateOnly],now,"g",new Set(["a"]),new Set(["1001"]))).toEqual([continuing,dateOnly,row]);
    expect(upcomingTiming(dateOnly,now)).toBe("Today · time not set");
    expect(upcomingTiming(row,now)).toBe("In 1h 30m");
    expect(upcomingTiming(continuing,now)).toBe("Scheduled now");
    expect(upcomingCalendarUrl(continuing,now)).toBe("/calendar?day=2028-02-29&occurrence=a");
  });
});
