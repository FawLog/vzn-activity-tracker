export type ActivityCell=Outcome|"mixed"|"recorded"|"not_registered"|"no_show"|"present_no_show";
export type Outcome="positive"|"negative"|"unknown"|"excused";
export interface Counts {positive:number;negative:number;unknown:number;excused:number;known:number;rate:number|null}
export interface Samples {samples:number;total:string|null;average:number|null;maximum:number|null}
export interface Metrics {observed_events:number;observed_sessions:number;registration?:Counts;attendance?:Counts;reliability?:Counts;no_shows?:number;missed_unregistered?:number;missed_registered?:number;damage?:Samples;points?:Samples;missions_completed?:Samples;personal_points?:Samples}
export const eventNames={alliance_championship:"Championship",bear_trap:"Bear Hunt",alliance_mobilization:"Mobilization",foundry:"Foundry",canyon:"Canyon"} as const;
export type EventKind=keyof typeof eventNames;
export interface ActivitySession {session_id:string;session_key:string;started_at:string;host_alliance_id:string|null;nickname:string;role:string|null;registration_outcome:Outcome;attendance_outcome:Outcome;metrics:Record<string,number>}
export type FoundryBattle = {session_key:string;started_at:string;alliance_id:string;outcome?:"victory"|"defeat"|null;own_score?:number|null;opponent_score?:number|null;opponent_tag?:string|null;opponent_name?:string|null;opponent_state?:string|null};
export interface ActivityEntry {event_id:string;event_type:string;occurred_on:string;alliance_id:string;alliance_name:string;home_alliance_id:string|null;cycle_attendance?:Outcome;cycle_registration?:Outcome;sessions:ActivitySession[]}
export interface ActivityPlayer {avatar_url?:string|null;fid:string;nickname:string|null;group_status:string;primary_alliance_id:string|null;metrics:Record<EventKind,Metrics>;history?:ActivityEntry[]}
export interface AnalyticsReport {group_id:string;alliance_id:string|null;start:string;end:string;published_events:number;players:ActivityPlayer[];events:Array<{id:string;event_type:string;occurred_on:string;recorded_players:number;unknown_home_players:number;metrics:Metrics;session_count:number;activity_cells:Record<string,ActivityCell>;contribution_points?:Record<string,string>;contribution_complete?:boolean;foundry_review_complete?:boolean;foundry_battles?:FoundryBattle[]}>;coverage:{events_with_sessions:number;events_without_sessions:number}}
export function period(days:number,now=new Date()){const end=now.toISOString().slice(0,10);const start=new Date(now);start.setUTCDate(start.getUTCDate()-days+1);return {start:start.toISOString().slice(0,10),end}}
export function formatTotal(value:string|null|undefined){return value==null?"—":BigInt(value).toLocaleString()}
export function compareCounts(a:Counts|undefined,b:Counts|undefined){if(!a?.known)return b?.known?1:0;if(!b?.known)return -1;return (a.rate??0)-(b.rate??0)||b.known-a.known}
export function eventName(key:string){return eventNames[key as EventKind]??key.replaceAll("_"," ")}
