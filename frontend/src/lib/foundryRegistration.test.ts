import {expect,it} from "vitest";
import {foundryRegistrationPreview,registrationCountsMatch} from "./foundryRegistration";
import type {ManualRow} from "./types";
const selected=(fid:string):ManualRow=>({fid,nickname:fid,registration:"registered",eligibility:"unknown",role:"main",registered_by:"unknown",attendance:"unknown",metrics:{}});
const legion=(session_key:string,fids:string[],registration_complete=true)=>({session_key,registration_complete,rows:fids.map(selected)});
it("keeps unlisted roster players unknown until both registration lists are verified, without battle results",()=>{
 const roster=["a","b","c","excused","ineligible"];
 const l1=legion("legion_1",["a"]),l2=legion("legion_2",["b"]);
 expect(foundryRegistrationPreview([l1],roster,["excused","ineligible"])).toEqual({complete:false,registered:["a"],notRegistered:[],unknown:["b","c"],excluded:["excused","ineligible"]});
 expect(foundryRegistrationPreview([l1,{...l2,registration_complete:false}],roster).notRegistered).toEqual([]);
 expect(foundryRegistrationPreview([l1,l2],roster,["excused","ineligible"])).toEqual({complete:true,registered:["a","b"],notRegistered:["c"],unknown:[],excluded:["excused","ineligible"]});
});
it("deduplicates roster and never marks players outside the reviewed roster unregistered",()=>{
 expect(foundryRegistrationPreview([legion("legion_1",["a"]),legion("legion_2",["b"])],["a","a","b","c"]).registered).toEqual(["a","b"]);
 expect(foundryRegistrationPreview([legion("legion_1",[]),legion("legion_1",[])],["c"]).unknown).toEqual(["c"]);
});

it("only offers full registration when both explicit counts match unique resolved roles",()=>{
 const rows=[selected("a"),{...selected("b"),role:"substitute" as const}];
 expect(registrationCountsMatch(rows,{main_count:1,substitute_count:1})).toBe(true);
 expect(registrationCountsMatch(rows,{main_count:1})).toBe(false);
 expect(registrationCountsMatch(rows,{main_count:2,substitute_count:1})).toBe(false);
 expect(registrationCountsMatch([...rows,rows[0]],{main_count:2,substitute_count:1})).toBe(false);
 expect(registrationCountsMatch([{...rows[0],role:null}],{main_count:1,substitute_count:0})).toBe(false);
 expect(registrationCountsMatch([rows[0]],{main_count:1,substitute_count:0})).toBe(true);
 expect(registrationCountsMatch([],{main_count:0,substitute_count:0})).toBe(true);
});
it("switches all 46 unlisted players to not registered once both legions are reviewed",()=>{
 const roster=Array.from({length:103},(_,i)=>String(i));
 const l1=legion("legion_1",roster.slice(0,40)),l2=legion("legion_2",roster.slice(40,57),false);
 expect(foundryRegistrationPreview([l1,l2],roster).unknown).toHaveLength(46);
 const complete=foundryRegistrationPreview([l1,{...l2,registration_complete:true}],roster);
 expect(complete.registered).toHaveLength(57);expect(complete.notRegistered).toHaveLength(46);expect(complete.unknown).toHaveLength(0);
});
