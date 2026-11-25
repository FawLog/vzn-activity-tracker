import {expect,it} from "vitest";
import {compareCounts,formatTotal,period} from "./analytics";
it("uses inclusive UTC date periods",()=>expect(period(7,new Date("2026-11-26T00:00:00Z"))).toEqual({start:"2026-11-20",end:"2026-11-26"}));
it("keeps unavailable rates below known rates including zero",()=>{const zero={positive:0,negative:1,unknown:0,excused:0,known:1,rate:0};expect(compareCounts(undefined,zero)).toBe(1);expect(compareCounts(zero,undefined)).toBe(-1)});
it("preserves precise raw totals",()=>expect(formatTotal("9007199254740993").replace(/[^0-9]/g,"")).toBe("9007199254740993"));
