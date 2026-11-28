import {addDays} from "./calendar";
import type {ScheduleFields} from "./schedule-editor";
export type CycleKind="canyon"|"svs";
export type CycleCreate={kind:CycleKind;request_key:string;phases:ScheduleFields[]};
export function cycleDraft(kind:CycleKind,monday:string,state:string,alliance:string|null):ScheduleFields[]{
  const day=new Date(monday+"T00:00Z");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(monday)||!Number.isFinite(day.getTime())||day.toISOString().slice(0,10)!==monday||day.getUTCDay()!==1)throw Error("Choose a Monday UTC anchor");
  const common={scope:kind==="canyon"?"alliance" as const:"state" as const,alliance_id:kind==="canyon"?alliance:null,state_id:state,confidence:"estimated" as const};
  const datePhase=(event_type:string,phase:string,offset:number,end:number|null):ScheduleFields=>({...common,event_type,phase,precision:"date",starts_at:addDays(monday,offset),ends_at:end===null?null:addDays(monday,end)});
  if(kind==="canyon")return [datePhase("canyon","Voting",0,2),datePhase("canyon","Registration",2,4),datePhase("canyon","Matchmaking",4,5),datePhase("canyon","Battle",5,null)];
  return [
    {...common,event_type:"svs_preparation",phase:"Preparation",precision:"minute",starts_at:monday+"T00:00Z",ends_at:addDays(monday,5)+"T10:00Z"},
    {...common,event_type:"svs_battle",phase:"Battle",precision:"minute",starts_at:addDays(monday,5)+"T10:00Z",ends_at:addDays(monday,5)+"T22:00Z"}
  ];
}
