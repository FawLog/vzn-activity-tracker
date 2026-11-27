import type {ActivityPlayer,AnalyticsReport,Counts} from "./analytics";

export const overallWeights={attendance:50,contribution:30,reliability:20} as const;
type Dimension=keyof typeof overallWeights;
export type OverallRow={player:ActivityPlayer;score:number|null;attendance:number|null;contribution:number|null;reliability:number|null;missed:number;noShows:number;excused:number;unknown:number;unobserved:number;lastActivity:string|null;observed:number;expected:number;weight:number;provisional:boolean;contributionSamples:number;partialContribution:boolean};
const attendanceKinds=["bear_trap","foundry","canyon","alliance_championship"] as const;
const sum=(values:Array<Counts|undefined>,key:"positive"|"negative"|"unknown"|"excused")=>values.reduce((n,c)=>n+(c?.[key]??0),0);
const rate=(values:Array<Counts|undefined>)=>{const p=sum(values,"positive"),n=sum(values,"negative");return p+n?100*p/(p+n):null};

// Midrank percentile between observed peers, with identical scores tied.
// Explicit zero is a real observation; a missing score never enters the distribution.
export function relativePoints(points:Record<string,string>):Map<string,number>{
 const entries=Object.entries(points).filter(([,v])=>/^\d+$/.test(v)).map(([fid,v])=>({fid,value:BigInt(v)}));
 entries.sort((a,b)=>a.value===b.value?0:a.value<b.value?-1:1);
 const result=new Map<string,number>();
 if(entries.length<2)return result;
 for(let i=0;i<entries.length;){
  let j=i+1;while(j<entries.length&&entries[j].value===entries[i].value)j++;
  const percentile=100*(i+j-1)/2/(entries.length-1);
  for(let k=i;k<j;k++)result.set(entries[k].fid,percentile);
  i=j;
 }
 return result;
}
export function overallRows(report:AnalyticsReport):OverallRow[]{
 const events=report.events.filter(e=>e.event_type==="alliance_mobilization"||attendanceKinds.some(k=>k===e.event_type));
 const contribution=events.filter(e=>e.event_type==="alliance_mobilization").map(e=>({e,relative:relativePoints(e.contribution_points??{})}));
 return report.players.filter(p=>p.group_status==="active"&&(!report.alliance_id||p.primary_alliance_id===report.alliance_id)).map(player=>{
  const m=player.metrics;
  const attendanceCounts=attendanceKinds.map(k=>k==="alliance_championship"?m[k]?.registration:m[k]?.attendance);
  const reliabilityCounts=[m.foundry?.reliability,m.canyon?.reliability];
  const samples=contribution.filter(c=>c.relative.has(player.fid));
  const partialContribution=samples.some(c=>!c.e.contribution_complete);
  const values:Record<Dimension,number|null>={attendance:rate(attendanceCounts),reliability:rate(reliabilityCounts),contribution:samples.length?samples.reduce((n,c)=>n+c.relative.get(player.fid)!,0)/samples.length:null};
  let weight=0,total=0;
  for(const k of Object.keys(overallWeights) as Dimension[]){const value=values[k];if(value!==null){weight+=overallWeights[k];total+=overallWeights[k]*value}}
  const cells=events.map(e=>({e,cell:e.activity_cells[player.fid]}));
  const observed=cells.filter(({cell})=>cell!==undefined&&cell!=="unknown"&&cell!=="mixed").length;
  const unknown=cells.filter(({cell})=>cell==="unknown"||cell==="mixed").length;
  const unobserved=cells.filter(({cell})=>cell===undefined).length;
  const knownActivity=cells.filter(({cell,e})=>(cell==="positive"||cell==="present_no_show")||(e.event_type==="alliance_mobilization"&&/^\d+$/.test(e.contribution_points?.[player.fid]??"")&&BigInt(e.contribution_points![player.fid])>0n));
  const lastActivity=knownActivity.reduce<string|null>((latest,{e})=>latest===null||e.occurred_on>latest?e.occurred_on:latest,null);
  const knownAttendance=sum(attendanceCounts,"positive")+sum(attendanceCounts,"negative");
  return {player,...values,score:weight?total/weight:null,weight,missed:sum(attendanceCounts.slice(0,3),"negative"),noShows:sum(reliabilityCounts,"negative"),excused:sum(attendanceCounts,"excused"),unknown,unobserved,lastActivity,observed,expected:events.length,contributionSamples:samples.length,partialContribution,provisional:weight<100||partialContribution||cells.some(({e,cell})=>e.event_type==="foundry"&&e.foundry_review_complete===false&&cell!==undefined)||unknown+unobserved>0||knownAttendance+samples.length<3||sum(reliabilityCounts,"unknown")>0};
 });
}
export type OverallSort="score"|"name"|"attendance"|"contribution"|"reliability"|"missed"|"noShows"|"excused"|"lastActivity"|"coverage";
export function sortOverall(rows:OverallRow[],key:OverallSort,descending:boolean){
 const value=(r:OverallRow)=>key==="name"?(r.player.nickname??r.player.fid):key==="coverage"?(r.expected?r.observed/r.expected:null):r[key];
 return [...rows].sort((a,b)=>{
  const x=value(a),y=value(b);
  if(x===null||y===null)return x===null?(y===null?a.player.fid.localeCompare(b.player.fid):1):-1;
  const cmp=typeof x==="string"&&typeof y==="string"?x.localeCompare(y):Number(x)-Number(y);
  return (descending?-1:1)*cmp||a.player.fid.localeCompare(b.player.fid);
 });
}
