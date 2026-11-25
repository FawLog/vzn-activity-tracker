import type { Player } from "./types";
import { normalizeName } from "./ocrParser";
type Candidate = Pick<Player,"fid"|"nickname">;
const compact = (s:string) => normalizeName(s).normalize("NFKD").replace(/\p{M}/gu,"").replace(/[^\p{L}\p{N}]/gu,"");
function distance(a:string,b:string):number {
 const x=Array.from(a),y=Array.from(b);let prev=y.map((_,i)=>i+1);prev.unshift(0);
 for(let i=0;i<x.length;i++){const next=[i+1];for(let j=0;j<y.length;j++)next.push(Math.min(next[j]+1,prev[j+1]+1,prev[j]+(x[i]===y[j]?0:1)));prev=next}
 return prev[y.length];
}
function score(name:string,other:string):number {
 const a=compact(name),b=compact(other);if(!a||!b)return 0;
 if(a===b)return 1;
 const length=Math.max(Array.from(a).length,Array.from(b).length);
 if(Math.min(Array.from(a).length,Array.from(b).length)<4)return 0;
 return 1-distance(a,b)/length;
}
function ranked<T extends Candidate>(name:string,players:T[]){return players.map(p=>({p,score:score(name,p.nickname??"")})).sort((a,b)=>b.score-a.score||(a.p.nickname??"").localeCompare(b.p.nickname??"")||a.p.fid.localeCompare(b.p.fid))}
export function rankedPlayers<T extends Candidate>(name:string,players:T[]):T[]{return ranked(name,players).map(x=>x.p)}
export function matchPlayer(name:string,players:Candidate[]):{fid:string;match:"exact"|"suggested"|"unknown"}{
 const exact=players.filter(p=>p.nickname&&normalizeName(p.nickname)===normalizeName(name));
 if(exact.length===1)return {fid:exact[0].fid,match:"exact"};
 if(exact.length>1)return {fid:"",match:"unknown"};
 const [first,second]=ranked(name,players);
 if(first&&first.score>=.78&&first.score-(second?.score??0)>=.12&&compact(name).length>=4)return {fid:first.p.fid,match:"suggested"};
 return {fid:"",match:"unknown"};
}
