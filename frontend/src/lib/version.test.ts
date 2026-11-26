import {describe,it,expect} from "vitest";
import {versionState} from "./version";
const a="a".repeat(40), b="a".repeat(39)+"b";
describe("production version status",()=>{
 it("detects missed webhook even when browser and server match",()=>{
  expect(versionState(a,a,{sha:b,ci:"success"},false)).toEqual({kind:"stale",label:"Update pending"});
 });
 it("compares full SHA and distinguishes stale browser",()=>{
  expect(versionState(a,b,{sha:b,ci:"success"},false).label).toBe("Reload required");
  expect(versionState(b,b,{sha:b,ci:"success"},false).label).toBe("Up to date");
 });
 it("distinguishes CI running, failed, and unknown",()=>{
  expect(versionState(a,a,{sha:b,ci:"running"},false).label).toBe("CI running");
  expect(versionState(a,a,{sha:b,ci:"failed"},false).label).toBe("CI failed");
  expect(versionState(a,a,{sha:b,ci:"unknown"},false).label).toContain("CI unknown");
 });
 it("never claims current from matching local builds without GitHub",()=>{
  expect(versionState(a,a,null,false).kind).toBe("unknown");
  expect(versionState(a,null,{sha:a,ci:"success"},false).kind).toBe("unknown");
  expect(versionState(null,a,{sha:a,ci:"success"},false).kind).toBe("unknown");
  expect(versionState(a,a,{sha:a,ci:"success"},true).kind).toBe("unknown");
 });
});
