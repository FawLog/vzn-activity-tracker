import type {ActivityPlayer,AnalyticsReport,Counts,EventKind,Metrics,Samples} from "./analytics";
export type Category="contribution"|"attendance"|"reliability";
export type MetricKey="points"|"missions_completed"|"damage"|"personal_points";
export type Measure="total"|"average"|"maximum";
export type RankingOption={key:string;label:string;event:EventKind;metric?:MetricKey;count?: "registration"|"attendance"|"reliability"};
export const options:Record<Category,RankingOption[]>={
 contribution:[{key:"mobi_points",label:"Mobilization points",event:"alliance_mobilization",metric:"points"},{key:"mobi_missions",label:"Mobilization completed missions",event:"alliance_mobilization",metric:"missions_completed"},{key:"bear_damage",label:"Bear Hunt damage (informational)",event:"bear_trap",metric:"damage"},{key:"foundry_points",label:"Foundry personal points (informational)",event:"foundry",metric:"personal_points"},{key:"canyon_points",label:"Canyon personal points (informational)",event:"canyon",metric:"personal_points"}],
 attendance:[{key:"bear",label:"Bear Hunt cycles",event:"bear_trap",count:"attendance"},{key:"champ",label:"Championship registration",event:"alliance_championship",count:"registration"},{key:"foundry",label:"Foundry attendance",event:"foundry",count:"attendance"},{key:"canyon",label:"Canyon attendance",event:"canyon",count:"attendance"}],
 reliability:[{key:"foundry",label:"Foundry registered legions",event:"foundry",count:"reliability"},{key:"canyon",label:"Canyon registered legions",event:"canyon",count:"reliability"}]
};
export type RankRow={player:ActivityPlayer;metrics:Metrics;samples?:Samples;counts?:Counts;missing:number;complete:boolean;value:string|number|null;rank:number|null;registered:number|null};
export type SortKey="rank"|"name"|"value"|"samples"|"positive"|"negative"|"unknown"|"excused"|"registered";
export function compareValue(a:string|number|null,b:string|number|null):number{
 if(a===null)return b===null?0:1;if(b===null)return -1;
 if(typeof a==="string"&&typeof b==="string"){const x=BigInt(a),y=BigInt(b);return x>y?1:x<y?-1:0}
 return Number(a)-Number(b);
}
export function rankingRows(report:AnalyticsReport,option:RankingOption,measure:Measure):RankRow[]{
 const events=report.events.filter(e=>e.event_type===option.event);
 const rows=report.players.map(player=>{
  const metrics=player.metrics[option.event],samples=option.metric?metrics[option.metric]:undefined,counts=option.count?metrics[option.count]:undefined;
  const missing=Math.max(0,events.length-metrics.observed_events);
  // Absence of a historical record is not evidence of eligibility or absence.
  // Keep partial rates visible, but never give them an ordinal leaderboard rank.
  const fullyObserved=missing===0&&events.every(e=>e.session_count>0);
  const complete=!!counts&&fullyObserved&&counts.unknown===0&&counts.known>0&&(option.event==="bear_trap"||option.event==="alliance_championship"||option.count==="attendance"||metrics.observed_sessions===events.reduce((n,e)=>n+e.session_count,0))&&(option.count!=="reliability"||metrics.registration?.unknown===0);
  const value=option.metric?(samples?.[measure]??null):(counts?.rate??null);
  return {player,metrics,samples,counts,missing,complete,value,rank:null,registered:option.count==="reliability"?(metrics.registration?.positive??0):null} as RankRow;
 });
 const eligible=rows.filter(r=>r.value!==null&&(option.metric?!!r.samples?.samples:r.complete)).sort((a,b)=>compareValue(b.value,a.value)||a.player.fid.localeCompare(b.player.fid));
 let rank=0;eligible.forEach((r,i)=>{if(i===0||compareValue(r.value,eligible[i-1].value)!==0)rank=i+1;r.rank=rank});
 return rows;
}
export function sortRows(rows:RankRow[],key:SortKey,descending:boolean){
 const val=(r:RankRow):string|number|null=>key==="rank"?r.rank:key==="value"?r.value:key==="samples"?r.samples?.samples??null:key==="registered"?r.registered:key==="unknown"?(r.counts?.unknown??0)+r.missing:key==="name"?null:r.counts?.[key]??null;
 return [...rows].sort((a,b)=>{
  if(key==="name")return (descending?-1:1)*(a.player.nickname??a.player.fid).localeCompare(b.player.nickname??b.player.fid)||a.player.fid.localeCompare(b.player.fid);
  const x=val(a),y=val(b);if(x===null||y===null)return x===null?(y===null?0:1):-1;
  return (descending?-1:1)*compareValue(x,y)||(a.player.nickname??a.player.fid).localeCompare(b.player.nickname??b.player.fid)||a.player.fid.localeCompare(b.player.fid);
 });
}
