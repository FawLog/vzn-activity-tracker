import { Search, UserPlus } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PageHeader } from "../components/Page";
import { api, type PlayerAffiliationFilter } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { formatDate } from "../lib/format";
import { navigate } from "../lib/router";
import type { Player } from "../lib/types";

type AffiliationSelection = "all" | "unconfirmed" | `alliance:${string}`;

function toPlayerFilter(selection: AffiliationSelection): PlayerAffiliationFilter {
  if (selection === "unconfirmed") return { mode: "unconfirmed" };
  if (selection.startsWith("alliance:")) return { mode: "alliance", allianceId: selection.slice("alliance:".length) };
  return { mode: "all" };
}

export function PlayersPage() {
  const { alliances, selectedGroup } = useGroupContext();
  const initialQuery = new URLSearchParams(window.location.search).get("q") ?? "";
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [sort, setSort] = useState("nickname");
  const [direction, setDirection] = useState("asc");
  const [selection, setSelection] = useState<AffiliationSelection>("all");
  const [selectionGroupId, setSelectionGroupId] = useState<string | null>(null);
  const [players, setPlayers] = useState<Player[] | null>(null);
  const [error, setError] = useState("");

  const effectiveSelection = selectionGroupId === selectedGroup?.id && (
    selection === "all" || selection === "unconfirmed" || alliances.some((alliance) => `alliance:${alliance.id}` === selection)
  ) ? selection : "all";
  const playerFilter = useMemo(() => toPlayerFilter(effectiveSelection), [effectiveSelection]);

  useEffect(() => {
    if (selectedGroup) {
      setSelection("all");
      setSelectionGroupId(selectedGroup.id);
    }
  }, [selectedGroup?.id]);

  useEffect(() => {
    setPlayers(null);
    setError("");
    if (!selectedGroup) return;
    api.players(selectedGroup.id, submittedQuery, sort, direction, playerFilter).then((result) => setPlayers(result.items)).catch((requestError) => setError(requestError.message));
  }, [selectedGroup, submittedQuery, sort, direction, playerFilter]);

  if (!selectedGroup) return <div className="page"><EmptyState title="No active group" description="Set up a group before viewing its roster." action={<button className="button button--primary" onClick={() => navigate("/onboarding")}>Start setup</button>} /></div>;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmittedQuery(query.trim());
  };

  const selectAffiliation = (value: AffiliationSelection) => {
    setSelectionGroupId(selectedGroup.id);
    setSelection(value);
  };

  return (
    <div className="page">
      <PageHeader title="Players" description={`FID-based roster profiles in ${selectedGroup.name}. Alliance selection in the top bar does not hide unconfirmed profiles.`} action={<button className="button button--primary" onClick={() => navigate("/admin?mode=players")}><UserPlus size={17} />Add player</button>} />
      <div className="toolbar roster-toolbar">
        <form className="filter-search" onSubmit={submit}><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search FID or nickname" aria-label="Search players" /></form>
        <label className="select-control"><span>Affiliation</span><select aria-label="Roster affiliation" value={effectiveSelection} onChange={(event) => selectAffiliation(event.target.value as AffiliationSelection)}><option value="all">All players</option><option value="unconfirmed">Unconfirmed affiliation</option>{alliances.map((alliance) => <option key={alliance.id} value={`alliance:${alliance.id}`}>{alliance.alliance_type === "primary" ? "Primary alliance" : "Additional alliance"} · {alliance.name}</option>)}</select></label>
        <label className="select-control"><span>Sort</span><select value={`${sort}:${direction}`} onChange={(event) => { const [nextSort, nextDirection] = event.target.value.split(":"); setSort(nextSort); setDirection(nextDirection); }}><option value="nickname:asc">Nickname A–Z</option><option value="nickname:desc">Nickname Z–A</option><option value="fid:asc">FID ascending</option><option value="created_at:desc">Newest first</option></select></label>
      </div>
      {error ? <ErrorState message={error} /> : !players ? <LoadingState label="Loading roster" /> : players.length === 0 ? (
        <EmptyState title={submittedQuery ? "No matching players" : "No players in this view"} description={submittedQuery ? "Try a different FID or nickname." : effectiveSelection === "unconfirmed" ? "No profiles without a confirmed primary alliance are available." : "Add the first FID-based roster record from Administration."} action={!submittedQuery && effectiveSelection === "all" && <button className="button button--primary" onClick={() => navigate("/admin?mode=players")}>Add player</button>} />
      ) : (
        <section className="data-panel data-panel--page">
          <div className="table-wrap"><table><thead><tr><th>FID</th><th>Nickname</th><th>Affiliation</th><th>Added</th><th aria-label="Open record" /></tr></thead><tbody>{players.map((player) => <tr key={player.fid} className="clickable-row"><td className="mono">{player.fid}</td><td><button className="table-link" onClick={() => navigate(`/players/${encodeURIComponent(player.fid)}`)}>{player.nickname ?? "Nickname unconfirmed"}</button></td><td>{player.primary_alliance_name ? player.primary_alliance_name : <span className="status status--draft">Unconfirmed</span>}</td><td>{formatDate(player.created_at)}</td><td className="row-arrow">→</td></tr>)}</tbody></table></div>
        </section>
      )}
    </div>
  );
}
