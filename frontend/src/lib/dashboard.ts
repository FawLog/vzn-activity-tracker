import type {AnalyticsReport,Counts,Metrics,ActivityCell,EventKind} from "./analytics";
import type {OverallRow} from "./overall";
export type TrendKind=EventKind;
export type DashboardKind=EventKind|"overall";
export function dimension(kind:EventKind):keyof Metrics{return kind==="alliance_championship"?"registration":kind==="bear_trap"?"attendance":kind==="alliance_mobilization"?"points":"reliability"}
export function combineCounts(values:(Counts|undefined)[]):Counts{const c={positive:0,negative:0,unknown:0,excused:0,known:0,rate:null as number|null};for(const v of values){if(v)for(const k of ["positive","negative","unknown","excused","known"] as const)c[k]+=v[k]}c.rate=c.known?Math.round(c.positive/c.known*10000)/100:null;return c}
export function eventCounts(report:AnalyticsReport,kind:EventKind){const key=dimension(kind);if(key==="points")return undefined;return combineCounts(report.events.filter(e=>e.event_type===kind).map(e=>e.metrics[key] as Counts|undefined))}
export function trend(report:AnalyticsReport,kind:EventKind){return report.events.filter(e=>e.event_type===kind).map(e=>({id:e.id,date:e.occurred_on,value:kind==="alliance_mobilization"?(e.metrics.points?.samples?e.metrics.points.average:null):((e.metrics[dimension(kind)] as Counts|undefined)?.rate??null),known:kind==="alliance_mobilization"?(e.metrics.points?.samples??0):((e.metrics[dimension(kind)] as Counts|undefined)?.known??0)}))}
export const heatLabels:Record<ActivityCell,string>={positive:"Confirmed positive",negative:"Confirmed negative",excused:"Excused / no duty",unknown:"Unknown / no record",mixed:"Mixed outcomes",recorded:"Score recorded"};
export const heatMarks:Record<ActivityCell,string>={positive:"+",negative:"−",excused:"E",unknown:"·",mixed:"±",recorded:"R"};
export function heatCell(event:AnalyticsReport["events"][number],fid:string):ActivityCell{return event.activity_cells?.[fid]??"unknown"}

export function heatmapEvents(report:AnalyticsReport,kind:DashboardKind){
 return report.events.filter(e=>kind==="overall"||e.event_type===kind).slice(-40);
}
export function overallDistribution(rows:OverallRow[]){
 const bins=[{label:"0–<25",count:0},{label:"25–<50",count:0},{label:"50–<75",count:0},{label:"75–100",count:0}];
 let covered=0,provisional=0,unscored=0;
 for(const row of rows){
  if(row.score===null){unscored++;continue}
  bins[Math.min(3,Math.max(0,Math.floor(row.score/25)))].count++;
  if(row.provisional)provisional++;else covered++;
 }
 return {bins,covered,provisional,unscored};
}
