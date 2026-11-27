import type {ManualSession} from "./types";

type RegistrationSession=Pick<ManualSession,"session_key"|"registration_complete"|"rows">;

/** Draft preview only; final historical roster and publication remain officer-attested. */
export function foundryRegistrationPreview(sessions:RegistrationSession[], roster:string[], exceptions:string[]=[]){
 const keys=new Set(sessions.map(s=>s.session_key));
 const complete=sessions.length===2&&keys.has("legion_1")&&keys.has("legion_2")&&sessions.every(s=>s.registration_complete);
 const selected=new Set(sessions.flatMap(s=>s.rows.filter(r=>r.registration==="registered").map(r=>r.fid)));
 const excludedFids=new Set(exceptions);
 const registered:string[]=[],notRegistered:string[]=[],unknown:string[]=[],excluded:string[]=[];
 for(const fid of new Set(roster)){
  if(excludedFids.has(fid))excluded.push(fid);
  else if(selected.has(fid))registered.push(fid);
  else if(complete)notRegistered.push(fid);
  else unknown.push(fid);
 }
 return {complete,registered,notRegistered,unknown,excluded};
}

/** Match the reviewed unique selected players to both explicit game counts. */
export function registrationCountsMatch(rows:ManualSession["rows"], details:ManualSession["foundry_details"]):boolean {
 const selected=rows.filter(r=>r.registration==="registered");
 const main=details?.main_count,sub=details?.substitute_count;
 return typeof main==="number"&&Number.isInteger(main)&&main>=0&&main<=30&&typeof sub==="number"&&Number.isInteger(sub)&&sub>=0&&sub<=10&&new Set(selected.map(r=>r.fid)).size===selected.length&&selected.every(r=>r.role==="main"||r.role==="substitute")&&selected.filter(r=>r.role==="main").length===main&&selected.filter(r=>r.role==="substitute").length===sub;
}
