import {describe,it,expect} from "vitest";
import {versionState} from "./version";
describe("production build status",()=>{
 it("matches full SHA, not its prefix",()=>{
  expect(versionState("a".repeat(40),"a".repeat(40),false).kind).toBe("current");
  expect(versionState("a".repeat(40),"a".repeat(39)+"b",false).kind).toBe("stale");
 });
 it("does not claim latest or verified on missing data",()=>{
  expect(versionState(null,"a".repeat(40),false).kind).toBe("unknown");
  expect(versionState("a".repeat(40),null,false).kind).toBe("unknown");
  expect(versionState("a".repeat(40),"a".repeat(40),true).kind).toBe("unknown");
 });
});
