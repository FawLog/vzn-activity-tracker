import {describe,it,expect} from "vitest";
import {gameEventForCalendar} from "./game-event-catalog";
import {advancedPlan,fixedGameInterval,forecastRows,intervalPayload,sourceRunWarning,stateAge,referenceEnd,referenceRepeat} from "./game-forecast";
import type {ScheduleFields} from "./schedule-editor";
const fields:ScheduleFields={event_type:"foundry",scope:"alliance",alliance_id:"a",state_id:"1001",starts_at:"2028-02-29",ends_at:null,precision:"date",phase:"",confidence:"confirmed"};
describe("anchored calendar forecast",()=>{
  it("uses fixed rules and refuses to guess cooldown and monthly schedules",()=>{
    expect(fixedGameInterval(gameEventForCalendar("foundry"))).toBe(20160);
    expect(fixedGameInterval(gameEventForCalendar("svs_preparation"))).toBe(40320);
    expect(fixedGameInterval(gameEventForCalendar("bear_trap"))).toBeNull();
    expect(fixedGameInterval(gameEventForCalendar("alliance_mobilization"))).toBeNull();
  });
  it("materializes an explicit UTC anchor, preserves precision and flags future estimates",()=>{
    expect(forecastRows(fields,3,20160)).toEqual([
      {start:"2028-02-29",end:null,confidence:"confirmed"},
      {start:"2028-03-14",end:null,confidence:"estimated"},
      {start:"2028-03-28",end:null,confidence:"estimated"}]);
    expect(forecastRows({...fields,starts_at:"2028-02-28T15:00Z",ends_at:"2028-02-28T15:30Z",precision:"minute"},2,2850)[1]).toEqual({start:"2028-03-01T14:30Z",end:"2028-03-01T15:00Z",confidence:"estimated"});
    expect(()=>intervalPayload(2,2850,"date")).toThrow();
    expect(()=>forecastRows({...fields,starts_at:"2028-02-30"},2,20160)).toThrow();
    expect(()=>forecastRows(fields,180,20160)).toThrow();
  });
  it("reports source inconsistencies and does not invent a date",()=>{
    expect(sourceRunWarning(gameEventForCalendar("svs_preparation"),"svs_preparation",fields).length).toBeGreaterThan(0);
    expect(stateAge("2028-01-01","2028-02-29")).toBe(59);
    expect(()=>stateAge("2028-03-01","2028-02-29")).toThrow();
    expect(gameEventForCalendar("svs_preparation")?.unlockDay).toBe(80);
  });
});

describe("variable calendar repeats",()=>{
  it("clamps each month from the original anchor and preserves duration",()=>{
    const plan=advancedPlan({...fields,starts_at:"2028-01-31",ends_at:"2028-02-02"},4,1440,"months",1,[]);
    expect(plan.rows.map(r=>r.start)).toEqual(["2028-01-31","2028-02-29","2028-03-31","2028-04-30"]);
    expect(plan.rows[1].end).toBe("2028-03-02");
  });
  it("uses selected weekdays without assuming a fixed gap",()=>{
    expect(advancedPlan({...fields,starts_at:"2028-02-29"},4,1440,"weekdays",1,[1,3]).rows.map(r=>r.start)).toEqual(["2028-02-29","2028-03-02","2028-03-07","2028-03-09"]);
    expect(()=>advancedPlan(fields,4,1440,"weekdays",1,[0])).toThrow();
  });
});

describe("reference duration",()=>{
  it("uses structured day and minute lengths without inventing unknown battle time",()=>{
    expect(referenceEnd(gameEventForCalendar("game:lucky-wheel"),{...fields,event_type:"game:lucky-wheel",starts_at:"2026-11-24"})).toBe("2026-11-27");
    expect(referenceEnd(gameEventForCalendar("foundry"),fields)).toBeNull();
    expect(referenceEnd(gameEventForCalendar("foundry"),{...fields,precision:"minute",starts_at:"2026-11-28T23:30Z"})).toBe("2026-11-29T00:30Z");
    expect(referenceEnd(gameEventForCalendar("alliance_showdown"),{...fields,event_type:"alliance_showdown",precision:"minute",starts_at:"2026-11-23T00:00Z"})).toBe("2026-11-29T12:00Z");
  });
});

it("uses inherited Flame and Fang interval and explicit month/variant rules",()=>{
 const flame=gameEventForCalendar("game:flame-and-fang");
 expect(fixedGameInterval(flame)).toBe(40320);
 expect(referenceEnd(flame,{...fields,event_type:"game:flame-and-fang",starts_at:"2026-12-07"})).toBe("2026-12-10");
 expect(referenceRepeat(gameEventForCalendar("game:fishing-tournament"))).toMatchObject({mode:"months",months:1,count:4});
 expect(referenceRepeat(gameEventForCalendar("game:romance-season"))).toMatchObject({mode:"months",months:12,count:2});
 expect(referenceRepeat(gameEventForCalendar("alliance_mobilization")).count).toBe(1);
 expect(referenceRepeat(gameEventForCalendar("game:king-of-icefield"),true)).toMatchObject({mode:"months",count:4});
 expect(referenceRepeat(gameEventForCalendar("game:crazy-joe")).count).toBe(1);
 const hall=gameEventForCalendar("game:hall-of-chief");
 expect(referenceEnd(hall,{...fields,event_type:"game:hall-of-chief",phase:"Season 2",starts_at:"2026-12-07"})).toBe("2026-12-14");
 expect(referenceEnd(hall,{...fields,event_type:"game:hall-of-chief",phase:"",starts_at:"2026-12-07"})).toBeNull();
 expect(referenceEnd(gameEventForCalendar("game:frostfire-mine"),{...fields,event_type:"game:frostfire-mine",precision:"minute",starts_at:"2026-12-07T21:00Z"})).toBe("2026-12-07T21:30Z");
 expect(referenceEnd(gameEventForCalendar("game:icefire-warhymn-league"),{...fields,event_type:"game:icefire-warhymn-league",starts_at:"2026-12-06"})).toBe("2026-12-13");
});
