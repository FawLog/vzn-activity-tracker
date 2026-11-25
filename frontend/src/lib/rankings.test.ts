import {expect,it} from "vitest";
import {options,rankingRows,sortRows} from "./rankings";
import type {ActivityPlayer,AnalyticsReport,Counts,Metrics} from "./analytics";
const blank:Metrics={observed_events:0,observed_sessions:0};
const counts=(positive:number,negative:number,unknown=0,excused=0):Counts=>({positive,negative,unknown,excused,known:positive+negative,rate:positive+negative?100*positive/(positive+negative):null});
function player(fid:string,m:Partial<ActivityPlayer["metrics"]>):ActivityPlayer{return {fid,nickname:fid,group_status:"active",primary_alliance_id:"a",metrics:{bear_trap:blank,alliance_championship:blank,alliance_mobilization:blank,foundry:blank,canyon:blank,...m}}}
function report(players:ActivityPlayer[],kind:string,n:number):AnalyticsReport{return {group_id:"g",alliance_id:"a",start:"2026-01-01",end:"2026-01-30",published_events:n,players,events:Array.from({length:n},(_,i)=>({id:String(i),event_type:kind,occurred_on:"2026-01-01",recorded_players:players.length,unknown_home_players:0,metrics:blank,session_count:1,activity_cells:{}})),coverage:{events_with_sessions:n,events_without_sessions:0}}}
it("ranks exact decimal totals and ties while preserving missing versus zero",()=>{
 const p=(fid:string,total:string|null)=>player(fid,{alliance_mobilization:{...blank,points:{samples:total===null?0:1,total,average:null,maximum:null}}});
 const rows=rankingRows(report([p("a","9007199254740993"),p("b","9007199254740992"),p("c","0"),p("d",null),p("e","9007199254740993")],"alliance_mobilization",1),options.contribution[0],"total");
 expect(sortRows(rows,"rank",false).map(r=>[r.player.fid,r.rank])).toEqual([["a",1],["e",1],["b",3],["c",4],["d",null]]);
 expect(sortRows(rows,"value",false).map(r=>r.player.fid)).toEqual(["c","b","a","e","d"]);
});
it("does not rank one known positive above fully observed attendance",()=>{
 const p=(fid:string,n:number,c:Counts)=>player(fid,{bear_trap:{observed_events:n,observed_sessions:n,attendance:c}});
 const rows=rankingRows(report([p("partial",1,counts(1,0)),p("unknown",3,counts(1,0,2)),p("covered",3,counts(2,1)),p("excused",3,counts(2,0,0,1)),p("zero",3,counts(0,3))],"bear_trap",3),options.attendance[0],"total");
 expect(sortRows(rows,"rank",false).map(r=>[r.player.fid,r.rank])).toEqual([["excused",1],["covered",2],["zero",3],["partial",null],["unknown",null]]);
 expect(rows[0].value).toBe(100);expect(rows[0].missing).toBe(2);
});
it("reliability uses only registered commitments and does not rank unknown registration",()=>{
 const p=(fid:string,reg:Counts,rel:Counts)=>player(fid,{foundry:{observed_events:2,observed_sessions:2,registration:reg,reliability:rel}});
 const rows=rankingRows(report([p("known",counts(1,1),counts(0,1)),p("partial",counts(1,0,1),counts(1,0)),p("no-duty",counts(0,2),counts(0,0))],"foundry",2),options.reliability[0],"total");
 expect(rows.map(r=>[r.player.fid,r.rank,r.registered])).toEqual([["known",1,1],["partial",null,1],["no-duty",null,0]]);
});
