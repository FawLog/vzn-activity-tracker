import { describe, expect, it } from "vitest";
import { templateFields, type ScheduleTemplateInput } from "./schedule-editor";

describe("alliance schedule templates",()=>{
  const base:ScheduleTemplateInput={event_type:"foundry",scope:"alliance",alliance_id:"a",state_id:"1001",starts_at:"2026-11-28T23:30Z",ends_at:"2026-11-29T00:30Z",precision:"minute",phase:"Legion 1",confidence:"confirmed",interval_minutes:20160,occurrence_count:4,rolling:true};
  it("rebases UTC time and duration without inheriting confirmed status",()=>{
    expect(templateFields(base,"2027-01-30")).toMatchObject({starts_at:"2027-01-30T23:30Z",ends_at:"2027-01-31T00:30Z",confidence:"estimated",alliance_id:"a",phase:"Legion 1"});
  });
  it("keeps an unknown time and end unknown",()=>{
    expect(templateFields({...base,precision:"date",starts_at:"2026-11-28",ends_at:null},"2027-01-30")).toMatchObject({starts_at:"2027-01-30",ends_at:null,precision:"date"});
  });
});
