import {expect,it} from "vitest";
import {combineCounts,heatCell,heatmapEvents,overallDistribution} from "./dashboard";
import type {AnalyticsReport} from "./analytics";
it("weights known outcomes, not event percentages",()=>{const c=combineCounts([{positive:1,negative:0,known:1,unknown:2,excused:0,rate:100},{positive:0,negative:9,known:9,unknown:0,excused:1,rate:0}]);expect(c.rate).toBe(10);expect(c.unknown).toBe(2)});
it("does not turn missing evidence into zero or absence",()=>{expect(combineCounts([]).rate).toBeNull();const e:AnalyticsReport["events"][number]={id:"event-1",event_type:"bear_trap",occurred_on:"2026-11-25",recorded_players:1,unknown_home_players:0,metrics:{observed_events:1,observed_sessions:1},session_count:1,activity_cells:{x:"positive"}};expect(heatCell(e,"y")).toBe("unknown");expect(heatCell(e,"x")).toBe("positive")});

import type {OverallRow} from "./overall";
it("shows all event types in overall mode and retains the last 40 events",()=>{
 const events=Array.from({length:42},(_,i)=>({id:String(i),event_type:i%2?"bear_trap":"alliance_championship",occurred_on:"2026-11-25",recorded_players:0,unknown_home_players:0,metrics:{observed_events:0,observed_sessions:0},session_count:0,activity_cells:{}}));
 const report={events} as AnalyticsReport;
 expect(heatmapEvents(report,"overall").map(e=>e.id)).toEqual(events.slice(2).map(e=>e.id));
 expect(heatmapEvents(report,"bear_trap").every(e=>e.event_type==="bear_trap")).toBe(true);
});
it("distributes real zero and 100 without counting missing scores",()=>{
 const rows=[{score:0,provisional:true},{score:25,provisional:false},{score:74,provisional:true},{score:100,provisional:false},{score:null,provisional:true}] as OverallRow[];
 const d=overallDistribution(rows);
 expect(d.bins.map(b=>b.count)).toEqual([1,1,1,1]);
 expect([d.covered,d.provisional,d.unscored]).toEqual([2,2,1]);
});
