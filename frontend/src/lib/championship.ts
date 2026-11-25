import type {ManualRow,ManualSession} from "./types";
export function championshipRows(rows:ManualRow[],complete:boolean):ManualRow[]{
 return rows.map(r=>{
  if(r.eligibility==="no_duty"||r.registration==="excused")return {...r,registration:"excused",role:null,registered_by:null};
  return {...r,eligibility:complete?"confirmed":"unknown",registration:r.registration==="registered"?"registered":complete?"not_registered":"unknown"};
 });
}
export function championshipSummary(rows:ManualRow[],complete:boolean){
 const result={registered:0,notRegistered:0,unknown:0,excused:0};
 for(const row of championshipRows(rows,complete)){
  if(row.registration==="registered")result.registered++;
  else if(row.registration==="not_registered")result.notRegistered++;
  else if(row.registration==="excused")result.excused++;
  else result.unknown++;
 }
 return result;
}
export function invalidateChampionship(session:ManualSession):ManualSession{
 return {...session,roster_complete:false,registration_complete:false,rows:championshipRows(session.rows,false)};
}
