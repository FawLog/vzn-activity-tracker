export function versionState(build:string|null,server:string|null,loading:boolean):{kind:"current"|"stale"|"unknown";label:string}{
 if(loading)return {kind:"unknown",label:"Checking…"};
 if(!build||!server)return {kind:"unknown",label:"Version unverified"};
 if(build!==server)return {kind:"stale",label:"UI / server differ"};
 return {kind:"current",label:"Builds match"};
}
