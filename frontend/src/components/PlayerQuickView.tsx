import { FurnaceLevel } from "./FurnaceLevel";
import { Swords, Crosshair } from "lucide-react";
import {useEffect,useRef,useState} from "react";
import {X,ExternalLink} from "lucide-react";
import {api} from "../lib/api";
import {navigate} from "../lib/router";
import {formatAllianceRank,formatTimestamp} from "../lib/format";
import type {Player} from "../lib/types";
import type {OverallRow} from "../lib/overall";
import type {ActivityPlayer} from "../lib/analytics";
import {PlayerAvatar} from "./PlayerAvatar";
import {PlayerActivity} from "./PlayerActivity";
import {LoadingState,ErrorState} from "./Feedback";

const fmt=(n:number|null)=>n===null?"—":n.toFixed(1)+"%";
export function PlayerQuickView({groupId,activityPlayer,row,start,end,onClose}:{groupId:string;activityPlayer:ActivityPlayer;row?:OverallRow;start:string;end:string;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 const closeButton=useRef<HTMLButtonElement>(null);
 const [player,setPlayer]=useState<Player|null>(null),[error,setError]=useState("");
 const fid=activityPlayer.fid;
 useEffect(()=>{
  const el=dialog.current!;
  const previous=document.activeElement;
  const overflow=document.body.style.overflow;
  el.showModal();document.body.style.overflow="hidden";closeButton.current?.focus();
  return ()=>{if(el.open)el.close();document.body.style.overflow=overflow;if(previous instanceof HTMLElement&&previous.isConnected)previous.focus({preventScroll:true})};
 },[]);
 useEffect(()=>{let live=true;api.player(groupId,fid).then(p=>{if(live)setPlayer(p)}).catch(e=>{if(live)setError(String(e.message))});return()=>{live=false}},[groupId,fid]);
 return <dialog ref={dialog} className="player-quick-view" aria-labelledby="quick-view-title" onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose()}}}>
  <header className="quick-view-toolbar"><h2 id="quick-view-title">Player quick view</h2><div className="quick-view-actions"><button className="button button--secondary" onClick={()=>{onClose();navigate("/players/"+encodeURIComponent(fid))}}><ExternalLink size={16}/>Full profile</button><button ref={closeButton} type="button" className="button button--quiet" aria-label="Close player quick view" onClick={onClose}><X size={20}/></button></div></header>
  <div className="quick-view-content">
   <div className="quick-view-identity"><PlayerAvatar url={player?.avatar_url??activityPlayer.avatar_url} large/><div><h3>{player?.nickname??activityPlayer.nickname??fid}</h3><p className="mono">ID {fid}</p><p>{player?.observed_alliance_name??player?.primary_alliance_name??""}</p></div></div>
   {row?<section className="data-panel"><div className="section-header"><div><h2>Overall activity</h2><p>{start} — {end} UTC · selected ranking scope · {row.provisional?"Provisional evidence":"Covered evidence"}</p></div></div><div className="profile-stats">
    <div><small>Activity score</small><strong>{row.score===null?"—":row.score.toFixed(1)}</strong></div><div><small>Coverage</small><strong>{row.observed}/{row.expected}</strong></div>
    <div><small>Attendance / registration</small><strong>{fmt(row.attendance)}</strong></div><div><small>Contribution</small><strong>{fmt(row.contribution)}</strong></div>
    <div><small>Reliability</small><strong>{fmt(row.reliability)}</strong></div><div><small>Missed / no-show</small><strong>{row.missed} / {row.noShows}</strong></div>
    <div><small>Excused / no duty</small><strong>{row.excused}</strong></div><div><small>Last activity</small><strong>{row.lastActivity??"—"}</strong></div>
   </div></section>:<p className="activity-explainer">Overall screening is not available for this player in the selected active roster. Historical event records remain available below.</p>}
   {error?<ErrorState message={error}/>:!player?<LoadingState label="Loading game profile"/>:<section className="data-panel"><div className="section-header"><div><h2>Game profile</h2><p>{player.stats_observed_at?"Updated "+formatTimestamp(player.stats_observed_at):"Latest available game data"}</p></div></div><div className="profile-stats">
    <div><small className="game-label"><Swords size={16} aria-hidden="true"/><span>Power</span></small><strong>{player.power?.toLocaleString()??"—"}</strong></div><div><small className="game-label"><Crosshair size={16} aria-hidden="true"/><span>Kills</span></small><strong>{player.kills?.toLocaleString()??"—"}</strong></div><div><small>Furnace</small><strong><FurnaceLevel level={player.furnace_level}/></strong></div><div><small>Alliance rank</small><strong>{formatAllianceRank(player.alliance_rank)}</strong></div><div><small>State</small><strong>{player.state_id??"—"}</strong></div><div><small>Alliance</small><strong>{player.observed_alliance_name??player.primary_alliance_name??"—"}</strong></div>
   </div></section>}
   <section className="data-panel"><div className="section-header"><div><h2>Foundry participation</h2><p>One attendance outcome per event; reliability per selected legion.</p></div></div><div className="profile-stats"><div><small>Registration rate</small><strong>{fmt(activityPlayer.metrics.foundry.registration?.rate??null)}</strong></div><div><small>Attendance</small><strong>{fmt(activityPlayer.metrics.foundry.attendance?.rate??null)}</strong></div><div><small>Missed without registration</small><strong>{activityPlayer.metrics.foundry.missed_unregistered??0}</strong></div><div><small>Legion no-shows</small><strong>{activityPlayer.metrics.foundry.no_shows??0}</strong></div></div></section>
   <PlayerActivity groupId={groupId} fid={fid} range={{start,end}} onNavigate={onClose}/>
  </div>
 </dialog>;
}
