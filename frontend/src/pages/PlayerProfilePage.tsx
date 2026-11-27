import { FurnaceLevel } from "../components/FurnaceLevel";
import { Swords, Crosshair } from "lucide-react";
import { ArrowLeft, History, ShieldCheck, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { PlayerActivity } from "../components/PlayerActivity";
import { ErrorState, LoadingState } from "../components/Feedback";
import { PlayerAvatar } from "../components/PlayerAvatar";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { formatTimestamp, formatFurnaceLevel, formatAllianceRank } from "../lib/format";
import { navigate } from "../lib/router";
import type { Player } from "../lib/types";

export function PlayerProfilePage({ fid }: { fid: string }) {
  const { selectedGroup } = useGroupContext();
  const [player, setPlayer] = useState<Player | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setPlayer(null);
    setError("");
    if (selectedGroup) api.player(selectedGroup.id, fid).then(value => { if (active) setPlayer(value); }).catch(requestError => { if (active) setError(requestError.message); });
    return () => { active = false; };
  }, [fid, selectedGroup]);
  if (!selectedGroup) return <div className="page"><LoadingState label="Selecting group" /></div>;
  if (error) return <div className="page"><ErrorState message={error} action={<button className="button button--quiet" onClick={() => navigate("/players")}>Return to players</button>} /></div>;
  if (!player || player.fid !== fid) return <div className="page"><LoadingState label="Loading player record" /></div>;
  const alliance = player.observed_alliance_name ?? player.primary_alliance_name;
  const rank = formatAllianceRank(player.alliance_rank);
  return (
    <div className="page player-profile">
      <button className="back-link back-link--page" onClick={() => navigate("/players")}><ArrowLeft size={18} />Players</button>
      <header className="profile-header">
        <PlayerAvatar url={player.avatar_url} large />
        <div className="profile-identity">
          <span className="mono">ID {player.fid}</span>
          <h1>{player.nickname ?? "Nickname unconfirmed"}</h1>
          <p>{player.group_status === "unconfirmed" ? "Unconfirmed alliance" : alliance ?? "Alliance unconfirmed"}</p>
        </div>
      </header>
      <div className="profile-layout">
        <div className="profile-empty-stack">
          <section className="data-panel">
            <div className="section-header"><div><h2>Game profile</h2><p>{player.stats_observed_at ? "Updated " + formatTimestamp(player.stats_observed_at) : "Latest available game data"}</p></div><History size={18} aria-hidden="true" /></div>
            <div className="profile-stats">
              <div><small className="game-label"><Swords size={16} aria-hidden="true"/><span>Power</span></small><strong>{player.power?.toLocaleString() ?? "—"}</strong></div>
              <div><small className="game-label"><Crosshair size={16} aria-hidden="true"/><span>Kills</span></small><strong>{player.kills?.toLocaleString() ?? "—"}</strong></div>
              <div><small>Furnace</small><strong><FurnaceLevel level={player.furnace_level}/></strong></div>
              <div><small>Alliance rank</small><strong className={"roster-rank roster-rank--" + rank.toLowerCase()}>{rank}</strong></div>
              <div><small>State</small><strong>{player.state_id ?? "—"}</strong></div>
              <div><small>Alliance</small><strong>{alliance ?? "—"}</strong></div>
            </div>
          </section>
          {!!player.nickname_history?.length && <section className="data-panel">
            <div className="section-header"><div><h2>Nickname history</h2></div></div>
            <div className="history-list">{player.nickname_history.map(name => <div key={name.nickname + "-" + name.valid_from}><strong>{name.nickname}</strong><span>{formatTimestamp(name.valid_from)} — {name.valid_to ? formatTimestamp(name.valid_to) : "Current"}</span></div>)}</div>
          </section>}
        </div>
        <div className="profile-empty-stack">
          {!!player.stat_history?.length && <section className="data-panel">
            <div className="section-header"><div><h2>Game history</h2></div></div>
            <div className="history-list">{player.stat_history.map(entry => <div key={entry.source_observed_at + "-" + entry.alliance_id}><strong>{entry.power?.toLocaleString() ?? "—"} power · {entry.kills?.toLocaleString() ?? "—"} kills</strong><span>{formatTimestamp(entry.source_observed_at)} · Furnace {formatFurnaceLevel(entry.furnace_level)} · rank {formatAllianceRank(entry.alliance_rank)}</span></div>)}</div>
          </section>}
          {!!player.membership_history?.length && <section className="data-panel">
            <div className="section-header"><div><h2>Membership observations</h2></div></div>
            <div className="history-list">{player.membership_history.map(entry => <div key={entry.alliance_tag + "-" + entry.observed_at}><strong>{entry.alliance_name}</strong><span>{formatTimestamp(entry.observed_at)}</span></div>)}</div>
          </section>}
          
          <div className="principle-rail"><TrendingUp /><span><strong>Separate dimensions</strong><small>Contribution, attendance, and reliability remain separate; Overall is an advisory screening index.</small></span></div>
          <div className="principle-rail"><ShieldCheck /><span><strong>Unknown stays unknown</strong><small>Missing from a partial leaderboard never becomes zero.</small></span></div>
        </div>
      </div>
      <PlayerActivity key={selectedGroup.id+":"+fid} groupId={selectedGroup.id} fid={fid} />
    </div>
  );
}
