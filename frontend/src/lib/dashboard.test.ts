import {expect,it} from "vitest";
import {combineCounts,heatCell} from "./dashboard";
import type {AnalyticsReport} from "./analytics";
it("weights known outcomes, not event percentages",()=>{const c=combineCounts([{positive:1,negative:0,known:1,unknown:2,excused:0,rate:100},{positive:0,negative:9,known:9,unknown:0,excused:1,rate:0}]);expect(c.rate).toBe(10);expect(c.unknown).toBe(2)});
it("does not turn missing evidence into zero or absence",()=>{expect(combineCounts([]).rate).toBeNull();const e:AnalyticsReport["events"][number]={id:"event-1",event_type:"bear_trap",occurred_on:"2026-11-25",recorded_players:1,unknown_home_players:0,metrics:{observed_events:1,observed_sessions:1},session_count:1,activity_cells:{x:"positive"}};expect(heatCell(e,"y")).toBe("unknown");expect(heatCell(e,"x")).toBe("positive")});
