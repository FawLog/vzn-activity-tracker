import {describe,it,expect} from "vitest";
import {gameEventForCalendar} from "./game-event-catalog";
import {compareActions,scoringDays,sourceStageId,numberLabel,rankingTables} from "./event-rewards";
describe("pinned event scoring and rewards",()=>{
  it("uses SvS source points and milestone rewards without inventing expert thresholds",()=>{
    const event=gameEventForCalendar("svs_preparation")!;
    const days=scoringDays(event.details,"svs_preparation");
    expect(days).toHaveLength(5);
    expect(scoringDays(event.details,"svs_battle").map(d=>d.day)).toEqual(["Battle"]);
    expect(days[0].scoring?.find(r=>r.itemId==="fire-crystal")?.points).toBe(2000);
    expect(days[0].milestones?.[0].scoreTotal).toBe(30000);
    expect(days[0].allianceMilestones?.[0].scoreTotal).toBe(145000);
    expect(event.details.expertTiers?.[0].thresholds).toBeUndefined();
  });
  it("compares only identical action units and preserves unknown data",()=>{
    const rows=compareActions([{day:"1",scoring:[{action:"Use 1 FC",points:2000}]},{day:"2",scoring:[{action:"Use 10 FC",points:20000}]},{day:"3",scoring:[{action:"Use 1 FC",points:0}]}]);
    expect(rows[0].values).toEqual([2000,null,0]);
    expect(numberLabel(undefined)).toBe("Not available");
    expect(numberLabel(0)).toBe("0");
    expect(compareActions([{day:"1",scoring:[{action:"A",points:1},{action:"A",points:2}]}])[0].values).toEqual([null]);
  });
  it("keeps explicit variants, units and season stage IDs",()=>{
    const v=gameEventForCalendar("game:vision-of-dawn")!.details.versions!;
    expect(v.map(x=>x.name)).toEqual(["Before Fire Crystal age","Fire Crystal age"]);
    expect(v[0].tiers?.[0].scoreTotal).toBeUndefined();
    expect(v[1].tiers?.[0].scoreTotal).toBe(10);
    expect(gameEventForCalendar("game:lucky-wheel")?.details.scoreUnit).toBe("spins");
    expect(sourceStageId("game:hall-of-chief","Season 2","3")).toBe("s2-3");
    expect(scoringDays(gameEventForCalendar("game:hall-of-chief")!.details,"game:hall-of-chief","Season 1")).toHaveLength(6);
    expect(rankingTables(gameEventForCalendar("game:king-of-icefield")!.details)).toHaveLength(4);
  });
});
