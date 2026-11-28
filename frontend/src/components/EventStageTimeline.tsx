import { useState } from "react";
import type { CalendarOccurrence } from "../lib/calendar";
import { gameEventForCalendar } from "../lib/game-event-catalog";
import { stagePlan } from "../lib/calendar-stages";
import { EventRewards, StageRewards } from "./EventRewards";
import { sourceStageId } from "../lib/event-rewards";
import { formatDate } from "../lib/format";

export function EventStageTimeline({row}:{row:CalendarOccurrence}){
  const reference=gameEventForCalendar(row.event_type);
  const plan=stagePlan(row);
  const [selected,setSelected]=useState<string|null>(null);
  const stage=plan.stages.find(s=>s.id===selected)??plan.stages[0];
  const runs=reference?.schedule?.runs??[];
  const stageData=reference?.details.days?.find(d=>String(d.day)===sourceStageId(row.event_type,row.phase,stage?.id??""));
  if(!reference||row.schedule_status==="cancelled"||(!reference.stages.length&&!reference.phases?.length&&runs.length<2))return null;
  const dateLabel=(value:string)=>formatDate(value)+(row.precision==="minute"?" "+value.slice(11,16)+" UTC":"");
  return <section className="calendar-stage-timeline" aria-label="Event stages">
    <h3>Event stages</h3>
    <p>Reference only · Not independently confirmed · Saved event dates remain unchanged</p>
    {plan.warning&&<p>{plan.warning}</p>}
    {!!plan.stages.length&&<>
      <div className="calendar-stage-tabs" role="group" aria-label="Select event stage">
        {plan.stages.map(s=><button type="button" className="button button--quiet" key={s.id} aria-pressed={stage?.id===s.id} onClick={()=>setSelected(s.id)}>Day {s.id}</button>)}
      </div>
      {stage&&<div className="calendar-stage-detail"><strong>{stage.name}</strong><p>{dateLabel(stage.start)} — {dateLabel(stage.end)} (exclusive)</p>{stage.note&&<p>{stage.note}</p>}<small>Estimated stage within the saved event.</small>{stageData&&<StageRewards stage={stageData} unit={reference.details.scoreUnit}/>}</div>}
    </>}
    {!plan.stages.length&&!!reference.stages.length&&<ol>{reference.stages.map((s,i)=><li key={s.id+"-"+i}>{s.id}: {s.name??"Stage name unavailable"}</li>)}</ol>}
    {!!runs.length&&<details><summary>Reference schedule and phases</summary><ul>{runs.map((r,i)=><li key={i}>{r.label??"Run"} · {r.startWeekday??"Weekday not specified"} · {r.startTimeUtc?r.startTimeUtc+" UTC":"Time not set"} · {r.length} {r.unit}</li>)}</ul>{!!reference.phases?.length&&<ol>{reference.phases.map((p,i)=><li key={i}><strong>{p.name}</strong> — {p.description}</li>)}</ol>}</details>}
    {!runs.length&&!!reference.phases?.length&&<ol>{reference.phases.map((p,i)=><li key={i}><strong>{p.name}</strong> — {p.description}</li>)}</ol>}
    {row.event_type==="canyon"&&<p>Voting, registration and matchmaking are reference phases. No additional dates have been inferred from this occurrence.</p>}
    <details><summary>All tasks and rewards</summary><EventRewards key={row.id} event={reference} eventType={row.event_type} phase={row.phase}/></details>
  </section>;
}
