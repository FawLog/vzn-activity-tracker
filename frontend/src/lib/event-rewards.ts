// Keep original action units, reward pack counts and source notes. No inferred zeros.
export interface Reward {name:string;amount?:number;note?:string;itemId?:string;decorationId?:string}
export interface Scoring {action:string;points?:number;itemId?:string;itemIds?:string[];note?:string}
export interface Rank {groupRanking:string;rewards?:Reward[];note?:string;starChange?:number|string}
export interface RankTable {basedOn?:string;name?:string;rankings?:Rank[]}
export interface Milestone {name?:string;scoreTotal?:number;rewards?:Reward[];note?:string}
export interface StageData {day:string;name?:string;note?:string;victoryPoints?:number;scoring?:Scoring[];milestones?:Milestone[];allianceMilestones?:Milestone[]}
export interface Mission {group?:string;name:string;points?:number;rewards?:Reward[];note?:string;levels?:number;levelRequirements?:{level:number;requirement:string}[]}
export interface Tier extends Milestone {rankings?:Rank[];milestones?:Milestone[];allianceMilestones?:Milestone[];personalRankings?:Rank[];allianceRankings?:Rank[]}
export interface ExpertTier {expertId:string;skill:string;tier:number;unlockSkillLevel:number;thresholds?:{days:string[];scoreTotal:number}[];rewards?:Reward[]}
export interface EventDetailsData {
  days?:StageData[];missions?:Mission[];missionPointsLabel?:string;scoreUnit?:string;
  tiers?:Tier[];rewards?:Reward[];personalRankings?:RankTable[];allianceRankings?:Rank[];allianceRankingUpdates?:RankTable[];
  expertTiers?:ExpertTier[];pointLevels?:{personalPoints?:number;alliancePoints?:number;rewards?:Reward[];reward?:Reward;level?:number;note?:string}[];
  damageRewards?:{minDamage:number;maxDamage?:number;rewards?:Reward[]}[];
  versions?:{name:string;note?:string;missions?:Mission[];tiers?:Tier[];days?:StageData[]}[];
}
export const numberLabel=(n:number|undefined)=>typeof n==="number"&&Number.isFinite(n)?n.toLocaleString("en-US"):"Not available";
export function scoringDays(data:EventDetailsData,eventType?:string,phase?:string):StageData[]{
  const rows=data.days??[];
  if(eventType==="svs_preparation")return rows.filter(d=>/^[1-5]$/.test(String(d.day)));
  if(eventType==="svs_battle")return rows.filter(d=>String(d.day)==="Battle");
  if(eventType==="game:hall-of-chief"){
    const season=phase?.trim().toLowerCase();
    if(season==="season 1"||season==="season 2")return rows.filter(d=>String(d.day).startsWith(season==="season 1"?"s1-":"s2-"));
  }
  return rows;
}
export function sourceStageId(eventType:string,phase:string,projectedId:string):string{
  if(eventType==="game:hall-of-chief"){
    const season=phase.trim().toLowerCase();
    if(season==="season 1"||season==="season 2")return (season==="season 1"?"s1-":"s2-")+projectedId;
  }
  return projectedId;
}
// Exact source wording only: item links may represent different quantities or constraints.
export function compareActions(days:StageData[]){
  const actions=[...new Set(days.flatMap(d=>(d.scoring??[]).map(r=>r.action)))];
  return actions.map(action=>({action,values:days.map(d=>{
    const matches=(d.scoring??[]).filter(r=>r.action===action);
    return matches.length===1&&typeof matches[0].points==="number"&&Number.isFinite(matches[0].points)?matches[0].points:null;
  })}));
}
export function rankingTables(data:EventDetailsData){
  return [
    ...(data.personalRankings??[]).map((t,i)=>({name:t.basedOn??t.name??"Personal ranking "+(i+1),rankings:t.rankings??[]})),
    ...(data.allianceRankings?.length?[{name:"Alliance ranking",rankings:data.allianceRankings}]:[]),
    ...(data.allianceRankingUpdates??[]).map((t,i)=>({name:t.name??"Alliance ranking update "+(i+1),rankings:t.rankings??[]})),
  ];
}
