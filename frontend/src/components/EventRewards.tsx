import {useState} from "react";
import {compareActions,numberLabel,rankingTables,scoringDays,type EventDetailsData,type Reward,type StageData,type Milestone,type Rank,type Tier,type Mission} from "../lib/event-rewards";
import type {GameEventSummary} from "../lib/game-event-catalog";

function RewardList({items}:{items?:Reward[]}){
  return items?.length?<ul className="game-reward-list">{items.map((r,i)=><li key={i}><strong>{r.name}</strong> · {numberLabel(r.amount)}{r.note&&<small> · {r.note}</small>}</li>)}</ul>:<p>Reward details not available.</p>;
}
function Milestones({items,title,unit="points"}:{items?:Milestone[];title:string;unit?:string}){
  if(!items?.length)return null;
  return <section><h4>{title}</h4>{items.map((m,i)=><details key={i}><summary>{m.name??"Milestone "+(i+1)} · {numberLabel(m.scoreTotal)} {m.scoreTotal!==undefined?unit:""}</summary><RewardList items={m.rewards}/>{m.note&&<p>{m.note}</p>}</details>)}</section>;
}
function Rankings({rows,title}:{rows?:Rank[];title:string}){
  if(!rows?.length)return null;
  return <details><summary>{title}</summary>{rows.map((r,i)=><details key={i}><summary>{r.groupRanking}{r.starChange!==undefined?" · Star change: "+r.starChange:""}</summary><RewardList items={r.rewards}/>{r.note&&<p>{r.note}</p>}</details>)}</details>;
}
function Tiers({tiers,unit}:{tiers?:Tier[];unit:string}){
  if(!tiers?.length)return null;
  return <details><summary>Reward tiers ({tiers.length})</summary>{tiers.map((t,i)=><details key={i}><summary>{t.name??"Tier "+(i+1)}{t.scoreTotal!==undefined?" · "+numberLabel(t.scoreTotal)+" "+unit:""}</summary>{t.note&&<p>{t.note}</p>}{t.rewards&&<RewardList items={t.rewards}/>}<Milestones title="Personal rewards" items={t.milestones} unit={unit}/><Milestones title="Alliance rewards" items={t.allianceMilestones} unit={unit}/><Rankings rows={t.rankings} title="Placement rewards"/><Rankings rows={t.personalRankings} title="Personal ranking"/><Rankings rows={t.allianceRankings} title="Alliance ranking"/>{!t.rewards?.length&&!t.rankings?.length&&!t.milestones?.length&&!t.allianceMilestones?.length&&!t.personalRankings?.length&&!t.allianceRankings?.length&&<p>Detailed rewards not available.</p>}</details>)}</details>;
}
function Missions({items,unit}:{items?:Mission[];unit:string}){
  if(!items?.length)return null;
  return <details><summary>Missions ({items.length})</summary>{items.map((m,i)=><details key={i}><summary>{m.group?m.group+" · ":""}{m.name} · {numberLabel(m.points)} {unit}</summary>{m.note&&<p>{m.note}</p>}{m.levelRequirements?.map((l,i)=><p key={i}>Level {l.level}: {l.requirement}</p>)}{m.levels!==undefined&&<p>Levels: {m.levels}</p>}<RewardList items={m.rewards}/></details>)}</details>;
}
export function StageRewards({stage,unit="points"}:{stage:StageData;unit?:string}){
  return <div className="game-event-rewards">
    {stage.victoryPoints!==undefined&&<p>Victory points: {numberLabel(stage.victoryPoints)}</p>}
    {stage.note&&<p>{stage.note}</p>}
    <h4>Scoring tasks</h4>
    {stage.scoring?.length?<div className="game-reward-scroll"><table><thead><tr><th scope="col">Action (source units)</th><th scope="col">{unit}</th></tr></thead><tbody>{stage.scoring.map((r,i)=><tr key={i}><td>{r.action}{r.note&&<small> · {r.note}</small>}</td><td>{numberLabel(r.points)}</td></tr>)}</tbody></table></div>:<p>Scoring data not available.</p>}
    <Milestones title="Personal milestones" items={stage.milestones} unit={unit}/>
    <Milestones title="Alliance milestones" items={stage.allianceMilestones} unit={unit}/>
  </div>;
}
export function EventRewards({event,eventType,phase}:{event:GameEventSummary;eventType?:string;phase?:string}){
  const [version,setVersion]=useState("");
  const [selected,setSelected]=useState("");
  const [query,setQuery]=useState("");
  const data=event.details;
  const variant=data.versions?.find(v=>v.name===version);
  const current:EventDetailsData=variant?{...data,...variant,versions:undefined}:data;
  const days=scoringDays(current,eventType,phase);
  const stage=days.find(d=>String(d.day)===selected)??days[0];
  const unit=current.scoreUnit??"points";
  const missionUnit=current.missionPointsLabel??unit;
  const comparison=compareActions(days).filter(r=>r.action.toLowerCase().includes(query.trim().toLowerCase()));
  const available=days.length||data.missions?.length||data.versions?.length||data.tiers?.length||data.rewards?.length||data.personalRankings?.length||data.allianceRankings?.length||data.allianceRankingUpdates?.length||data.expertTiers?.length||data.damageRewards?.length||data.pointLevels?.length;
  if(!available)return null;
  return <section className="game-event-rewards" aria-label="Event tasks and rewards">
    <h3>Event tasks &amp; rewards</h3>
    <p>Game reference only. Verify your state, event version and expert bonuses in game. Missing values are not zero.</p>
    {!!data.versions?.length&&<label>Event version<select value={version} onChange={e=>{setVersion(e.target.value);setSelected("");}}><option value="">Select version explicitly</option>{data.versions.map(v=><option key={v.name} value={v.name}>{v.name}</option>)}</select></label>}
    {variant?.note&&<p>{variant.note}</p>}
    {!!days.length&&<><label>Scoring stage<select value={String(stage.day)} onChange={e=>setSelected(e.target.value)}>{days.map((d,i)=><option key={i} value={String(d.day)}>{d.day} · {d.name??"Stage name unavailable"}</option>)}</select></label><StageRewards stage={stage} unit={unit}/></>}
    {days.length>1&&<details><summary>Compare scoring across stages</summary><p>Exact action wording and source units only. A dash means not listed or ambiguous; never assume zero. Points across different events are not equivalent rewards.</p><label>Find action<input value={query} onChange={e=>setQuery(e.target.value)}/></label><div className="game-reward-scroll"><table><thead><tr><th scope="col">Action</th>{days.map((d,i)=><th key={i} scope="col">{d.day}</th>)}</tr></thead><tbody>{comparison.map((r,i)=><tr key={i}><td>{r.action}</td>{r.values.map((v,j)=><td key={j}>{v===null?"—":numberLabel(v)}</td>)}</tr>)}</tbody></table></div>{!comparison.length&&<p>No matching actions.</p>}</details>}
    <Missions items={current.missions} unit={missionUnit}/>
    <Tiers tiers={current.tiers} unit={unit}/>
    {rankingTables(current).map((r,i)=><Rankings key={i} title={r.name} rows={r.rankings}/>)}
    {!!current.rewards?.length&&<details><summary>General event rewards</summary><RewardList items={current.rewards}/></details>}
    {!!current.expertTiers?.length&&<details><summary>Expert extra tiers</summary>{current.expertTiers.map((t,i)=><details key={i}><summary>{t.expertId} · {t.skill} · Tier {t.tier} · Skill level {t.unlockSkillLevel}</summary>{t.thresholds?.length?t.thresholds.map((v,j)=><p key={j}>Stages {v.days.join(", ")}: {numberLabel(v.scoreTotal)} points</p>):<p>Point threshold not available.</p>}<RewardList items={t.rewards}/></details>)}</details>}
    {!!current.damageRewards?.length&&<details><summary>Per-run damage rewards</summary><p>Source does not define which adjacent range owns the exact boundary.</p>{current.damageRewards.map((t,i)=><details key={i}><summary>{numberLabel(t.minDamage)} — {t.maxDamage===undefined?"and above":numberLabel(t.maxDamage)}</summary><RewardList items={t.rewards}/></details>)}</details>}
    {!!current.pointLevels?.length&&<details><summary>Personal and alliance point levels</summary>{current.pointLevels.map((t,i)=><details key={i}><summary>Level {t.level??i+1} · Personal {numberLabel(t.personalPoints)} · Alliance {numberLabel(t.alliancePoints)}</summary><RewardList items={t.rewards??(t.reward?[t.reward]:undefined)}/>{t.note&&<p>{t.note}</p>}</details>)}</details>}
  </section>;
}
