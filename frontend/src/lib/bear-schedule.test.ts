import {describe,expect,it} from "vitest";
import {bearSchedulePlan} from "./bear-schedule";
const slots=[{alliance_id:"a",time:"23:30",nextDay:false},{alliance_id:"b",time:"00:30",nextDay:true}];
describe("Bear batch schedule",()=>{
  it("uses a single shared day with independent cross-midnight slots",()=>{
    const result=bearSchedulePlan("2090-06-01",48,slots,true);
    expect(result.count).toBe(31);
    expect(result.payload.traps).toEqual([{alliance_id:"a",starts_at:"2090-06-01T23:30Z"},{alliance_id:"b",starts_at:"2090-06-02T00:30Z"}]);
    expect(result.cycles[1].date).toBe("2090-06-03");
    expect(result.cycles[1].traps[1].start).toBe("2090-06-04T00:30Z");
  });
  it("supports 47.5 hours and optional finite forecast",()=>{
    const result=bearSchedulePlan("2090-06-01",47.5,slots,false);
    expect(result.count).toBe(4);
    expect(result.cycles[1].traps[0].start).toBe("2090-06-03T23:00Z");
    expect(result.payload.rolling).toBe(false);
  });
  it("rejects incomplete or duplicate slots and invalid cycles",()=>{
    expect(()=>bearSchedulePlan("2090-06-01",48,[slots[0],slots[0]],true)).toThrow();
    expect(()=>bearSchedulePlan("2090-06-01",48,[slots[1]],true)).toThrow();
    expect(()=>bearSchedulePlan("2090-06-01",48,[{...slots[0],time:""}],true)).toThrow();
    expect(()=>bearSchedulePlan("2090-06-01",47,slots,true)).toThrow();
    expect(()=>bearSchedulePlan("2090-02-30",48,slots,true)).toThrow();
  });
});
