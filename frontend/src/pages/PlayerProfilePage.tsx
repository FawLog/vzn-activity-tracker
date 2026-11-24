import { ArrowLeft, History, ShieldCheck, TrendingUp, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { api } from "../lib/api";
import { formatTimestamp } from "../lib/format";
import { navigate } from "../lib/router";
import type { Player } from "../lib/types";

export function PlayerProfilePage({ fid }: { fid: string }) {
  const [player, setPlayer] = useState<Player | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.player(fid).then(setPlayer).catch((requestError) => setError(requestError.message)); }, [fid]);
  if (error) return <div className="page"><ErrorState message={error} action={<button className="button button--quiet" onClick={() => navigate("/players")}>Return to players</button>} /></div>;
  if (!player) return <div className="page"><LoadingState label="Loading player record" /></div>;
  return <div className="page"><button className="back-link back-link--page" onClick={() => navigate("/players")}><ArrowLeft size={18} />Players</button><header className="profile-header"><span className="profile-header__icon"><UserRound /></span><div><span className="mono">FID {player.fid}</span><h1>{player.nickname}</h1><p>Roster identity record</p></div></header><div className="profile-layout"><section className="data-panel"><div className="section-header"><div><h2>Identity history</h2><p>Nicknames remain linked to the primary FID.</p></div><History size={20} /></div><div className="history-list">{player.nickname_history?.map((name) => <div key={`${name.nickname}-${name.valid_from}`}><strong>{name.nickname}</strong><span>{formatTimestamp(name.valid_from)} — {name.valid_to ? formatTimestamp(name.valid_to) : "Current"}</span></div>)}</div></section><section className="profile-empty-stack"><EmptyState compact title="No event history" description="Verified event records for this player will appear here." /><div className="principle-rail"><TrendingUp /><span><strong>Separate dimensions</strong><small>Contribution, attendance, and reliability are never collapsed into one score.</small></span></div><div className="principle-rail"><ShieldCheck /><span><strong>Unknown stays unknown</strong><small>Missing from a partial leaderboard never becomes zero.</small></span></div></section></div></div>;
}
