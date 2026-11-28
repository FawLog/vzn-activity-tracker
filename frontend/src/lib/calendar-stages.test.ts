import {describe,it,expect} from "vitest";
import {eventDay,stagePlan,stagesOn} from "./calendar-stages";
import type {CalendarOccurrence} from "./calendar";
const row:CalendarOccurrence={id:"test",group_id:"g",series_id:null,sequence:0,event_type:"svs_preparation",scope:"state",alliance_id:null,state_id:"4284",starts_at:"2028-01-03T00:00Z",ends_at:"2028-01-08T10:00Z",precision:"minute",phase:"",confidence:"confirmed",schedule_status:"scheduled",source:"manual",revision:1};
describe("reference stage projection",()=>{
  it("uses five SvS preparation stages, extends day five and never changes the parent",()=>{
    const plan=stagePlan(row);
    expect(plan.stages.map(s=>s.name)).toEqual(["City Construction","Basic Skills Up","Beast Slay","Hero Development","Power Boost"]);
    expect(plan.stages[4].end).toBe("2028-01-08T10:00Z");
    expect(stagesOn(row,"2028-01-08").map(s=>s.id)).toEqual(["5"]);
    expect(eventDay(row,"2028-01-08")).toBe("Day 6 of 6");
    expect(row.confidence).toBe("confirmed");
    expect(plan.warning).toContain("conflicts");
  });
  it("clips to confirmed end and does not invent a missing time",()=>{
    const short={...row,ends_at:"2028-01-08T00:00Z"};
    expect(stagePlan(short).stages[4].end).toBe(short.ends_at);
    expect(stagesOn(short,"2028-01-08")).toEqual([]);
    expect(stagePlan({...row,ends_at:null}).stages).toEqual([]);
    expect(stagePlan({...row,starts_at:"2028-01-03T08:00Z"}).stages).toEqual([]);
    expect(stagePlan({...row,schedule_status:"cancelled"}).stages).toEqual([]);
  });
  it("keeps Canyon battle separate from reference phases",()=>{
    expect(stagePlan({...row,event_type:"canyon"}).stages).toEqual([]);
    for(const event_type of ["svs_battle","svs_matchmaking","svs_triage"])expect(stagePlan({...row,event_type}).stages).toEqual([]);
  });
  it("requires explicit Hall of Chief season",()=>{
    const hoc={...row,event_type:"game:hall-of-chief",precision:"date" as const,starts_at:"2028-01-03",ends_at:"2028-01-10"};
    expect(stagePlan(hoc).stages).toEqual([]);
    expect(stagePlan({...hoc,phase:"Season 2"}).stages).toHaveLength(7);
  });
  it("date only remains date only",()=>{
    const plan=stagePlan({...row,precision:"date",starts_at:"2028-01-03",ends_at:"2028-01-08"});
    expect(plan.stages[4].end).toBe("2028-01-08");
  });
});
