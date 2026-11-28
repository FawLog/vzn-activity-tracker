import {describe,it,expect} from "vitest";
import {creationEventOptions,creationType} from "./calendar-event-options";
describe("one creation choice per game event",()=>{
 it("hides standalone aliases while preserving the original event types for edits",()=>{
  expect(new Set(creationEventOptions.map(([,label])=>label)).size).toBe(creationEventOptions.length);
  for(const name of ["Bear Trap","Foundry Battle","Canyon Clash","State of Power (SvS)"])expect(creationEventOptions.filter(([,label])=>label===name)).toHaveLength(1);
  expect(creationType("svs_battle")).toBe("cycle:svs");
 });
});
