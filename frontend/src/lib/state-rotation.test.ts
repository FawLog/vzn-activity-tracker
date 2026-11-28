import {describe,it,expect} from "vitest";
import {progression,reviewRotation} from "./state-rotation";
import type {CalendarOccurrence} from "./calendar";
const row=(date:string,extra:Partial<CalendarOccurrence>={}):CalendarOccurrence=>({id:date,group_id:"g",series_id:null,sequence:0,event_type:"game:lucky-wheel",scope:"state",alliance_id:null,state_id:"1001",starts_at:date,ends_at:null,precision:"date",phase:"",confidence:"confirmed",schedule_status:"scheduled",source:"manual",revision:1,...extra});
const get=(rows:CalendarOccurrence[],type="game:lucky-wheel")=>reviewRotation(rows,"1001","2026-04-04","2026-11-28").find(r=>r.type===type)!;
describe("state progression and rotation",()=>{
  it("uses the pinned milestone days without turning them into confirmed calendar dates",()=>{
    const result=progression("2026-04-04","2026-11-28");
    expect(result.age).toBe(238);
    expect(result.currentGeneration).toBe(4);
    expect(result.upcoming.find(m=>m.day===270)?.date).toBe("2026-12-30");
  });
  it("anchors a date-only rotation to actual confirmed local Tuesdays",()=>{
    const result=get([row("2026-11-17"),row("2026-11-03")]).forecast!;
    expect(result.fields).toMatchObject({starts_at:"2026-12-01",ends_at:null,precision:"date",confidence:"estimated",scope:"state"});
    expect(result.interval).toBe(20160);
    expect(result.count).toBe(5);
  });
  it("refuses to infer from estimates, another state, an alliance, contradictory dates or a cancellation",()=>{
    expect(get([row("2026-11-17",{confidence:"estimated"})]).forecast).toBeUndefined();
    expect(get([row("2026-11-17",{state_id:"1002"})]).forecast).toBeUndefined();
    expect(get([row("2026-11-17",{scope:"alliance",alliance_id:"a"})]).forecast).toBeUndefined();
    expect(get([row("2026-11-17"),row("2026-11-10")]).forecast).toBeUndefined();
    expect(get([row("2026-11-17"),row("2026-12-01",{schedule_status:"cancelled"})]).forecast).toBeUndefined();
    expect(get([row("2026-11-18")]).forecast).toBeUndefined();
  });
  it("does not turn a state unlock into an event anchor",()=>{
    expect(get([],"svs_preparation").forecast).toBeUndefined();
    const result=reviewRotation([row("2026-11-17",{event_type:"svs_preparation"})],"1001","2026-11-01","2026-11-28").find(r=>r.type==="svs_preparation");
    expect(result?.reason).toContain("unlock");
  });
});
