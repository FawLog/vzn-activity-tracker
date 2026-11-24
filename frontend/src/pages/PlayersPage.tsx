import { Search, UserPlus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { navigate } from "../lib/router";
import type { Player } from "../lib/types";

export function PlayersPage() {
  const initialQuery = new URLSearchParams(window.location.search).get("q") ?? "";
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [sort, setSort] = useState("nickname");
  const [direction, setDirection] = useState("asc");
  const [players, setPlayers] = useState<Player[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setPlayers(null);
    setError("");
    api.players(submittedQuery, sort, direction).then((result) => setPlayers(result.items)).catch((requestError) => setError(requestError.message));
  }, [submittedQuery, sort, direction]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmittedQuery(query.trim());
  };

  return (
    <div className="page">
      <PageHeader title="Players" description="FID-based roster records with nickname history." action={<button className="button button--primary" onClick={() => navigate("/admin?mode=players")}><UserPlus size={17} />Add player</button>} />
      <div className="toolbar">
        <form className="filter-search" onSubmit={submit}><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search FID or nickname" aria-label="Search players" /></form>
        <label className="select-control"><span>Sort</span><select value={`${sort}:${direction}`} onChange={(event) => { const [nextSort, nextDirection] = event.target.value.split(":"); setSort(nextSort); setDirection(nextDirection); }}><option value="nickname:asc">Nickname A–Z</option><option value="nickname:desc">Nickname Z–A</option><option value="fid:asc">FID ascending</option><option value="created_at:desc">Newest first</option></select></label>
      </div>
      {error ? <ErrorState message={error} /> : !players ? <LoadingState label="Loading roster" /> : players.length === 0 ? (
        <EmptyState title={submittedQuery ? "No matching players" : "No players yet"} description={submittedQuery ? "Try a different FID or nickname." : "Add the first FID-based roster record from Administration."} action={!submittedQuery && <button className="button button--primary" onClick={() => navigate("/admin?mode=players")}>Add player</button>} />
      ) : (
        <section className="data-panel data-panel--page">
          <div className="table-wrap"><table><thead><tr><th>FID</th><th>Nickname</th><th>Added</th><th aria-label="Open record" /></tr></thead><tbody>{players.map((player) => <tr key={player.fid} className="clickable-row"><td className="mono">{player.fid}</td><td><button className="table-link" onClick={() => navigate(`/players/${encodeURIComponent(player.fid)}`)}>{player.nickname}</button></td><td>{formatDate(player.created_at)}</td><td className="row-arrow">→</td></tr>)}</tbody></table></div>
        </section>
      )}
    </div>
  );
}
