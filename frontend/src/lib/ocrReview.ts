import type { ParsedRow } from "./ocrParser";
export type ReviewRow=ParsedRow & {fid:string;include:boolean;match:"exact"|"suggested"|"unknown"|"manual"};
export function summarizeReview(rows:ReviewRow[],eventType:string){
 const byFid=new Map<string,ReviewRow>();
 const conflicts=new Set<string>();
 let duplicates=0;
 const signature=(r:ReviewRow)=>eventType==="alliance_championship"?"registered":eventType==="bear_trap"?JSON.stringify([r.damage]):(eventType==="foundry_registration"||eventType==="canyon_registration")?JSON.stringify([r.role]):(eventType==="foundry_results"||eventType==="canyon_results")?JSON.stringify([r.points]):JSON.stringify([r.completed,r.total,r.points]);
 for(const row of rows){
   if(!row.include||!row.fid)continue;
   const first=byFid.get(row.fid);
   if(!first){byFid.set(row.fid,{...row});continue}
   if(signature(first)!==signature(row)||((eventType==="foundry_results"||eventType==="canyon_results")&&first.rank!==undefined&&row.rank!==undefined&&first.rank!==row.rank)){conflicts.add(row.fid);continue}
   duplicates++;
   byFid.set(row.fid,{...first,...((eventType==="foundry_results"||eventType==="canyon_results")&&first.rank===undefined&&row.rank!==undefined?{rank:row.rank}:{}),source:[...new Set([first.source,row.source])].join("; ")});
 }
 return {rows:[...byFid.values()],conflicts,duplicates};
}
