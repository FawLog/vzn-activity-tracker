import {describe,expect,it} from "vitest";
import {bearCycleDates,type ScheduleFields} from "./schedule-editor";
const fields:ScheduleFields={event_type:"bear_trap",scope:"alliance",alliance_id:"a",state_id:"1001",precision:"minute",starts_at:"2090-06-02T00:30Z",ends_at:null,phase:"",confidence:"estimated"};
describe("explicit recurring Bear grouping",()=>{
  it("uses the shared anchor rather than each trap's date",()=>{
    expect(bearCycleDates(fields,"2090-06-01T23:30Z","trap_2",3,2850,"fixed")).toEqual(["2090-06-01","2090-06-03","2090-06-05"]);
  });
  it("rejects date-only, different cycle and invalid keys",()=>{
    expect(()=>bearCycleDates({...fields,precision:"date"},"2090-06-01T23:30Z","trap_2",3,2850,"fixed")).toThrow();
    expect(()=>bearCycleDates(fields,"2090-06-03T23:30Z","trap_2",3,2850,"fixed")).toThrow();
    expect(()=>bearCycleDates(fields,"2090-06-01T23:30Z","trap_31",3,2850,"fixed")).toThrow();
  });
});
