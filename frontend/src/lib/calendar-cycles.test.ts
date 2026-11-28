import {describe,it,expect} from "vitest";
import {cycleDraft,cycleIntervalDays,cycleOccurrences,canyonBattleEnd,legionPhases,initialCycleCount,moveCyclePhaseStart} from "./calendar-cycles";
describe("reviewed event cycle draft",()=>{
  it("keeps Canyon battle time unknown and all dates estimated",()=>{
    const rows=cycleDraft("canyon","2028-01-03","4284","a");
    expect(rows.map(p=>p.starts_at)).toEqual(["2028-01-03","2028-01-05","2028-01-07","2028-01-08"]);
    expect(rows[3].ends_at).toBeNull();
    expect(rows.every(p=>p.precision==="date"&&p.confidence==="estimated")).toBe(true);
  });
  it("uses extended SvS preparation and separate battle",()=>{
    const rows=cycleDraft("svs","2028-01-03","4284","a");
    expect(rows[0].ends_at).toBe("2028-01-08T10:00Z");
    expect(rows[1].starts_at).toBe(rows[0].ends_at);
    expect(rows[1].alliance_id).toBeNull();
  });
  it("rejects a non-Monday anchor",()=>expect(()=>cycleDraft("svs","2028-01-04","4284",null)).toThrow());
});

it("previews repeated complete Canyon cycles, with unknown future battle times",()=>{
  const first=cycleDraft("canyon","2026-11-23","4284","a");
  expect(cycleIntervalDays("canyon")).toBe(28);
  first[3]={...first[3],precision:"minute",starts_at:"2026-11-28T15:00Z",confidence:"confirmed"};
  first[3].ends_at=canyonBattleEnd(first[3]);
  expect(first[3].ends_at).toBe("2026-11-28T16:00Z");
  const rows=cycleOccurrences("canyon",first,3,28);
  expect(rows[1].map(p=>p.starts_at)).toEqual(["2026-12-21","2026-12-23","2026-12-25","2026-12-26"]);
  expect(rows[1][3].ends_at).toBeNull();
  expect(rows[1].every(p=>p.confidence==="estimated")).toBe(true);
  expect(()=>cycleOccurrences("canyon",first,3,4)).toThrow();
});

it("builds Foundry from the supplement and keeps future legion times unknown",()=>{
 const rows=cycleDraft("foundry","2026-11-30","4284","a");
 expect(cycleIntervalDays("foundry")).toBe(14);
 expect(rows.map(p=>p.starts_at)).toEqual(["2026-11-30","2026-12-02","2026-12-04","2026-12-06"]);
 expect(rows[2].ends_at).toBe("2026-12-06");
 const split=legionPhases(rows,true);
 expect(split.slice(-2).map(p=>p.phase)).toEqual(["Legion 1","Legion 2"]);
 expect(cycleOccurrences("foundry",split,2,14)[1].slice(-2).map(p=>p.starts_at)).toEqual(["2026-12-20","2026-12-20"]);
});

it("initializes the whole-cycle renewal window for each reference cadence",()=>{
 expect(initialCycleCount(14,true,3)).toBe(5);
 expect(initialCycleCount(28,true,1)).toBe(3);
 expect(initialCycleCount(14,false,3)).toBe(3);
 expect(initialCycleCount(null,true,1)).toBe(1);
});


it("preserves reviewed phase duration and uses the phase reference after a precision change",()=>{
 const rows=cycleDraft("foundry","2026-11-30","4284","a");
 expect(moveCyclePhaseStart(rows[0],"2026-11-29").ends_at).toBe("2026-12-01");
 const custom={...rows[0],ends_at:"2026-12-01"};
 expect(moveCyclePhaseStart(custom,"2026-11-29").ends_at).toBe("2026-11-30");
 const timed={...rows[1],precision:"minute" as const,starts_at:"",ends_at:null};
 expect(moveCyclePhaseStart(timed,"2026-12-02T03:00Z").ends_at).toBe("2026-12-04T03:00Z");
 expect(moveCyclePhaseStart(rows[3],"2026-12-06").ends_at).toBeNull();
 expect(moveCyclePhaseStart({...rows[3],precision:"minute",starts_at:""},"2026-12-06T15:00Z").ends_at).toBe("2026-12-06T16:00Z");
});

it("rejects a future date-only battle that would overlap a timed matchmaking phase",()=>{
 const rows=cycleDraft("foundry","2026-11-30","4284","a");
 rows[2]={...rows[2],precision:"minute",starts_at:"2026-12-04T08:00Z",ends_at:"2026-12-06T08:00Z"};
 rows[3]={...rows[3],precision:"minute",starts_at:"2026-12-06T15:00Z",ends_at:"2026-12-06T16:00Z"};
 expect(cycleOccurrences("foundry",rows,1,14)).toHaveLength(1);
 expect(()=>cycleOccurrences("foundry",rows,2,14)).toThrow(/overlap/);
});
