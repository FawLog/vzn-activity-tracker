import {expect,it} from "vitest";
import type {ManualRow,ManualSession} from "./types";
import {championshipRows,championshipSummary,invalidateChampionship} from "./championship";
const row=(fid:string,registration:ManualRow["registration"]="unknown",eligibility:ManualRow["eligibility"]="unknown"):ManualRow=>({fid,nickname:fid,registration,eligibility,role:null,registered_by:null,attendance:"unknown",metrics:{}});
it("keeps a partial list unknown and marks the 11 missing players only after explicit complete review",()=>{
 const rows=Array.from({length:100},(_,i)=>row(String(i),i<89?"registered":"unknown"));
 expect(championshipSummary(rows,false)).toEqual({registered:89,notRegistered:0,unknown:11,excused:0});
 expect(championshipSummary(rows,true)).toEqual({registered:89,notRegistered:11,unknown:0,excused:0});
 expect(championshipRows(rows,true).every(r=>r.eligibility==="confirmed")).toBe(true);
});
it("preserves exceptions and invalidates derived negatives on edits",()=>{
 const rows=championshipRows([row("a","registered"),row("b"),row("c","unknown","no_duty"),row("d","excused")],true);
 const session:ManualSession={id:"s",session_key:"main",started_at:"2026-11-26T00:00:00Z",revision:1,roster_complete:true,registration_complete:true,attendance_complete:false,results_complete:false,rows};
 const next=invalidateChampionship(session);
 expect(next.roster_complete).toBe(false);expect(next.registration_complete).toBe(false);
 expect(championshipSummary(next.rows,false)).toEqual({registered:1,notRegistered:0,unknown:1,excused:2});
});
