import {expect,it} from "vitest";
import {overallRows,relativePoints,sortOverall} from "./overall";
import type {ActivityPlayer,AnalyticsReport,Counts,Metrics} from "./analytics";
const blank:Metrics={observed_events:0,observed_sessions:0};
const counts=(positive:number,negative:number,unknown=0,excused=0):Counts=>({positive,negative,unknown,excused,known:positive+negative,rate:positive+negative?100*positive/(positive+negative):null});
function player(fid:string,m:Partial<ActivityPlayer["metrics"]>={},status="active",alliance="a"):ActivityPlayer{return {fid,nickname:fid,group_status:status,primary_alliance_id:alliance,metrics:{bear_trap:blank,alliance_championship:blank,alliance_mobilization:blank,foundry:blank,canyon:blank,...m}}}
function report(players:ActivityPlayer[],events:AnalyticsReport["events"]=[]):AnalyticsReport{return {group_id:"g",alliance_id:"a",start:"2026-01-01",end:"2026-01-30",published_events:events.length,players,events,coverage:{events_with_sessions:events.length,events_without_sessions:0}}}
function event(kind:string,cells:AnalyticsReport["events"][number]["activity_cells"],points?:Record<string,string>,complete=false):AnalyticsReport["events"][number]{return {id:kind,event_type:kind,occurred_on:"2026-01-20",recorded_players:Object.keys(cells).length,unknown_home_players:0,metrics:blank,session_count:1,activity_cells:cells,contribution_points:points,contribution_complete:complete}}
it("normalizes exact point values, ties and real zero; excludes missing and singleton",()=>{
 expect([...relativePoints({a:"0",b:"9007199254740993",c:"9007199254740993",d:"9007199254740994"})]).toEqual([["a",0],["b",50],["c",50],["d",100]]);
 expect(relativePoints({a:"10"}).size).toBe(0);
});
it("uses 50/30/20 weights, excludes damage and excused, distinguishes missed commitment",()=>{
 const p=player("p",{bear_trap:{...blank,attendance:counts(1,0,0,1),damage:{samples:1,total:"99999999",average:99999999,maximum:99999999}},foundry:{...blank,attendance:counts(0,1),reliability:counts(0,1)},alliance_championship:{...blank,registration:counts(1,0)}});
 const events=[event("bear_trap",{p:"positive"}),event("foundry",{p:"negative"}),event("alliance_championship",{p:"positive"}),event("alliance_mobilization",{p:"recorded"},{p:"10",q:"0"},true)];
 const r=overallRows(report([p],events))[0];
 expect(r.score).toBeCloseTo(50*2/3+30);expect(r.weight).toBe(100);expect(r.missed).toBe(1);expect(r.noShows).toBe(1);expect(r.excused).toBe(1);expect(r.lastActivity).toBe("2026-01-20");
});
it("does not turn missing evidence into zero or penalize new members",()=>{
 const p=player("p",{bear_trap:{...blank,attendance:counts(1,0)}});
 const r=overallRows(report([p,player("new"),player("old",{},"archived"),player("academy",{},"active","b")],[event("bear_trap",{p:"positive"}),event("alliance_mobilization",{p:"unknown"})]));
 expect(r.map(x=>x.player.fid)).toEqual(["p","new"]);
 expect(r[0].score).toBe(100);expect(r[0].weight).toBe(50);expect(r[0].provisional).toBe(true);
 expect(r[1].score).toBeNull();expect(r[1].missed).toBe(0);
 expect(sortOverall(r,"score",false).map(x=>x.player.fid)).toEqual(["p","new"]);
});
it("labels partial contribution and sorts confirmed low activity before high",()=>{
 const r=overallRows(report([player("low"),player("high"),player("missing")],[event("alliance_mobilization",{low:"recorded",high:"recorded"},{low:"0",high:"100"})]));
 expect(r[0].score).toBe(0);expect(r[0].partialContribution).toBe(true);expect(r[1].score).toBe(100);expect(r[2].score).toBeNull();
 expect(sortOverall(r,"score",false).map(x=>x.player.fid)).toEqual(["low","high","missing"]);
});
