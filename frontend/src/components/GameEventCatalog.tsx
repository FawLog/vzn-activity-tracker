import { EventRewards } from "./EventRewards";
import { useState } from "react";
import { catalogVersion, gameEvents, repeatLabel, searchGameEvents, type GameEventSummary } from "../lib/game-event-catalog";

export function EventCatalogSummary({event}:{event:GameEventSummary}){
  return <div className="game-catalog-summary">
    <p>{event.description}</p>
    <p><strong>Game reference:</strong> {event.frequency??"Frequency unavailable"} · {event.duration??"Duration unavailable"}</p>
    <p>{repeatLabel(event.schedule?.repeat)}. Not a confirmed state schedule.</p>
    {!!event.schedule?.runs?.length&&<ul>{event.schedule.runs.map((run,i)=><li key={i}>{run.label?run.label+": ":""}{run.length} {run.unit}{run.startWeekday?" · "+run.startWeekday:""}{run.startTimeUtc?" · "+run.startTimeUtc+" UTC":""}</li>)}</ul>}
    {!!event.requirements?.length&&<details><summary>Participation requirements</summary><ul>{event.requirements.map((requirement,i)=><li key={i}>{requirement}</li>)}</ul></details>}
    {!!event.phases?.length&&<details><summary>Game phases</summary><ul>{event.phases.map((phase,i)=><li key={i}><strong>{phase.name}:</strong> {phase.description}</li>)}</ul></details>}
    {!!event.stages.length&&<details><summary>Scoring stage names</summary><ol>{event.stages.map((stage,i)=><li key={stage.id+"-"+i}>{stage.id}: {stage.name??"Stage name unavailable"}</li>)}</ol></details>}
    {(event.dayCount>0||event.missionCount>0||event.hasVariants)&&<p>Reference data available: {[event.dayCount?event.dayCount+" scoring stages":null,event.missionCount?event.missionCount+" missions":null,event.hasVariants?"event variants":null].filter(Boolean).join(" · ")}. See tasks and rewards below.</p>}
    <details><summary>Tasks and rewards</summary><EventRewards key={event.id} event={event}/></details>
    {event.scheduleOverride&&<p><a href={event.scheduleOverride.source} target="_blank" rel="noreferrer">Official schedule supplement</a> · checked {event.scheduleOverride.checkedOn}. {event.scheduleOverride.note}</p>}
    <small>Source: whiteout-survival-data {catalogVersion}. Verify against the in-game event.</small>
  </div>;
}
export function GameEventCatalog({onClose}:{onClose:()=>void}){
  const [query,setQuery]=useState("");
  const [category,setCategory]=useState("all");
  const [selected,setSelected]=useState<string|null>(null);
  const items=searchGameEvents(query,category);
  const categories=[...new Set(gameEvents.map(e=>e.category))].sort();
  return <section className="data-panel calendar-editor game-catalog" aria-label="Game event catalog">
    <div className="calendar-controls"><h2>Game event catalog</h2><button className="button button--quiet" onClick={onClose}>Close catalog</button></div>
    <p>Game reference only. Entries do not create or confirm scheduled events.</p>
    <div className="calendar-editor-fields">
      <label>Find game event<input value={query} onChange={e=>{setQuery(e.target.value);setSelected(null);}} placeholder="Search events"/></label>
      <label>Event category<select value={category} onChange={e=>{setCategory(e.target.value);setSelected(null);}}><option value="all">All categories</option>{categories.map(c=><option key={c} value={c}>{c}</option>)}</select></label>
    </div>
    <p>{items.length} of {gameEvents.length} events · {gameEvents.filter(e=>e.schedule).length} with schedule data</p>
    <div className="game-catalog-list">{items.map(event=><div key={event.id} className="game-catalog-item">
      <button className="game-catalog-row" aria-expanded={selected===event.id} onClick={()=>setSelected(selected===event.id?null:event.id)}>
        {event.icon&&<img src={event.icon} width={32} height={32} alt="" loading="lazy"/>}
        <span><strong>{event.name}</strong><small>{event.category} · {repeatLabel(event.schedule?.repeat)}</small></span>
      </button>
      {selected===event.id&&<EventCatalogSummary event={event}/>}
    </div>)}</div>
    {!items.length&&<p>No matching game events.</p>}
  </section>;
}
