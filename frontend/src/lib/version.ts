export type RepositoryVersion={sha:string;ci:string;checked_at?:string};
export const validSha=(value:unknown):string|null=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value)?value:null;
export function versionState(build:string|null,server:string|null,remote:RepositoryVersion|null,loading:boolean):{kind:"current"|"stale"|"failed"|"unknown";label:string}{
 if(loading)return {kind:"unknown",label:"Checking…"};
 if(!validSha(server)||!remote||!validSha(remote.sha))return {kind:"unknown",label:"Status unavailable"};
 if(server!==remote.sha){
  if(remote.ci==="success")return {kind:"stale",label:"Update pending"};
  if(remote.ci==="running")return {kind:"stale",label:"CI running"};
  if(remote.ci==="failed")return {kind:"failed",label:"CI failed"};
  return {kind:"stale",label:"Update required · CI unknown"};
 }
 if(!validSha(build))return {kind:"unknown",label:"Production current · UI unknown"};
 if(build!==server)return {kind:"stale",label:"Reload required"};
 return {kind:"current",label:"Up to date"};
}
