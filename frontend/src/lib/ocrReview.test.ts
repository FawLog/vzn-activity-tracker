import { expect,it } from "vitest";
import { summarizeReview,type ReviewRow } from "./ocrReview";
const row=(fid:string,nickname:string,extra:Partial<ReviewRow>={}):ReviewRow=>({fid,nickname,source:"a.png",include:true,match:"exact",...extra});
it("deduplicates by FID rather than OCR name for championship",()=>{
 const r=summarizeReview([row("1","Sora"),row("1","Sora #2",{source:"b.png"}),row("2","Fox")],"alliance_championship");
 expect(r.rows).toHaveLength(2);expect(r.duplicates).toBe(1);expect(r.conflicts.size).toBe(0);
});
it("deduplicates equal bear scores, but never selects between differing scores",()=>{
 const r=summarizeReview([row("1","Fox",{damage:4515319571}),row("1","F ox",{damage:4515319571}),row("1","Fox",{damage:1})],"bear_trap");
 expect(r.conflicts.has("1")).toBe(true);expect(r.duplicates).toBe(1);
});
it("ignores excluded rows and detects differing mission ratios",()=>{
 const a=row("1","Fox",{completed:3,total:4,points:20});
 const b=row("1","Fox",{completed:3,total:5,points:20});
 expect(summarizeReview([a,b],"alliance_mobilization").conflicts.has("1")).toBe(true);
 expect(summarizeReview([a,{...b,include:false}],"alliance_mobilization").conflicts.size).toBe(0);
});

it("merges overlapping Foundry results including zero and missing medal rank, but flags inconsistent points or role",()=>{
 const a=row("1","Old",{points:0}),b=row("1","New",{points:0,rank:25,source:"b.png"});
 const same=summarizeReview([a,b],"foundry_results");
 expect(same.rows[0].rank).toBe(25);expect(same.rows[0].points).toBe(0);expect(same.conflicts.size).toBe(0);
 expect(summarizeReview([a,{...b,points:10}],"foundry_results").conflicts.has("1")).toBe(true);
 expect(summarizeReview([row("1","Old",{role:"main"}),row("1","New",{role:"substitute"})],"foundry_registration").conflicts.has("1")).toBe(true);
});

it("flags conflicting Canyon registration roles and merges duplicates by FID",()=>{
 const a=row("1","Old",{role:"main"}),b=row("1","New",{role:"main",source:"b.png"});
 expect(summarizeReview([a,b],"canyon_registration").duplicates).toBe(1);
 expect(summarizeReview([a,{...b,role:"substitute"}],"canyon_registration").conflicts.has("1")).toBe(true);
});
