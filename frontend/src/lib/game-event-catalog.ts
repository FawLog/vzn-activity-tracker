import type { EventDetailsData } from "./event-rewards";
import { catalog, catalogVersion } from "virtual:wos-event-catalog";

export type RepeatRule =
  | {kind:"none"}
  | {kind:"every";every:number;unit:"hours"|"days"|"weeks"|"months"}
  | {kind:"weekly";weekdays:string[]};
export interface GameRun {
  label?:string;
  length:number;
  unit:"minutes"|"hours"|"days";
  startWeekday?:string;
  startTimeUtc?:string;
}
export interface GameStage {id:string;name?:string;note?:string}
export interface GameEventSummary {
  id:string;
  name:string;
  category:string;
  description:string;
  icon:string|null;
  frequency?:string;
  duration?:string;
  schedule?:{repeat?:RepeatRule;runs?:GameRun[]};
  requirements?:string[];
  phases?:{name:string;description:string}[];
  unlockDay?:number;
  stages:GameStage[];
  details:EventDetailsData;
  dayCount:number;
  missionCount:number;
  hasVariants:boolean;
}
export { catalogVersion };
export const gameEvents:readonly GameEventSummary[] = [...catalog].sort((a,b)=>a.name.localeCompare(b.name));
const byId = new Map(gameEvents.map(e=>[e.id,e]));
const calendarIds:Readonly<Record<string,string>> = {
  bear_trap:"bear-hunt", foundry:"foundry-battle", canyon:"canyon-clash",
  alliance_championship:"alliance-championship", alliance_mobilization:"alliance-mobilization",
  alliance_showdown:"alliance-showdown", svs_preparation:"svs-state-of-power",
  svs_battle:"svs-state-of-power", castle_battle:"sunfire-castle",
};
export function gameEventForCalendar(type:string):GameEventSummary|undefined {
  const id=type.startsWith("game:")?type.slice(5):calendarIds[type];
  return id?byId.get(id):undefined;
}
export function searchGameEvents(query:string,category:string="all"):GameEventSummary[]{
  const term=query.trim().toLowerCase();
  return gameEvents.filter(e=>(category==="all"||e.category===category)&&(!term||e.name.toLowerCase().includes(term)||e.id.includes(term)));
}
export function repeatLabel(rule?:RepeatRule):string{
  if(!rule)return "Repeat rule unavailable";
  if(rule.kind==="none")return "One-time event";
  if(rule.kind==="weekly")return "Weekly · "+rule.weekdays.join(", ");
  return "Every "+rule.every+" "+(rule.every===1?rule.unit.slice(0,-1):rule.unit);
}

export const extraCalendarEvents=gameEvents.filter(e=>!Object.values(calendarIds).includes(e.id));
