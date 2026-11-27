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
