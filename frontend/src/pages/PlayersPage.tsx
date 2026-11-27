import { FurnaceLevel } from "../components/FurnaceLevel";
import { ArrowDown, ArrowUp, ArrowUpDown, Search, UserPlus } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PlayerAvatar } from "../components/PlayerAvatar";
import { PageHeader } from "../components/Page";
import { api, type PlayerAffiliationFilter } from "../lib/api";
import { formatAllianceRank } from "../lib/format";
import { useGroupContext } from "../lib/group-context";
import { navigate } from "../lib/router";
import type { Player } from "../lib/types";

type SortColumn = "nickname" | "fid" | "power" | "kills" | "furnace_level" | "alliance_rank";
type SortDirection = "asc" | "desc";
type RosterSort = { column: SortColumn; direction: SortDirection };
const ROSTER_SORT_KEY = "vzn-roster-sort";
const SORT_COLUMNS: readonly SortColumn[] = ["nickname", "fid", "power", "kills", "furnace_level", "alliance_rank"];
const DEFAULT_SORT: RosterSort = { column: "power", direction: "desc" };

function readRosterSort(): RosterSort {
  try {
    const saved = JSON.parse(localStorage.getItem(ROSTER_SORT_KEY) ?? "null");
    if (saved && SORT_COLUMNS.includes(saved.column) && (saved.direction === "asc" || saved.direction === "desc")) return saved;
  } catch { /* Storage may be unavailable or contain an old value. */ }
  return DEFAULT_SORT;
}


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
  const [rosterSort, setRosterSort] = useState<RosterSort>(readRosterSort);
  const { column: sort, direction } = rosterSort;
  const [selection, setSelection] = useState<AffiliationSelection>("all");
  const [selectionGroupId, setSelectionGroupId] = useState<string | null>(null);
  const [players, setPlayers] = useState<Player[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const requestVersion = useRef(0);
  const previousScope = useRef("");
  const [refreshing, setRefreshing] = useState(false);

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
    const version = ++requestVersion.current;
    const scope = JSON.stringify([selectedGroup?.id, submittedQuery, playerFilter]);
    if (scope !== previousScope.current) setPlayers(null);
    previousScope.current = scope;
    setLoadingMore(false);
    setError("");
    if (!selectedGroup) { setRefreshing(false); return; }
    setRefreshing(true);
    api.players(selectedGroup.id, submittedQuery, sort, direction, playerFilter).then((result) => {
      if (requestVersion.current === version) { setPlayers(result.items); setTotal(result.total); }
    }).catch((requestError) => {
      if (requestVersion.current === version) setError(requestError.message);
    }).finally(() => {
      if (requestVersion.current === version) setRefreshing(false);
    });
    return () => { requestVersion.current++; };
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

  const loadMore = async () => {
    if (!selectedGroup || !players || loadingMore || refreshing) return;
    const version = requestVersion.current;
    setLoadingMore(true);
    try {
      const result = await api.players(selectedGroup.id, submittedQuery, sort, direction, playerFilter, 100, players.length);
      if (requestVersion.current === version) {
        setPlayers([...players, ...result.items]);
        setTotal(result.total);
      }
    } catch (requestError) {
      if (requestVersion.current === version) setError(requestError instanceof Error ? requestError.message : "Unable to load more players");
    } finally {
      if (requestVersion.current === version) setLoadingMore(false);
    }
  };

  const sortHeader = (column: SortColumn, label: string) => {
    const active = sort === column;
    const Icon = active ? (direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
    return (
      <th scope="col" aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : undefined}>
        <button type="button" className="roster-sort" onClick={() => {
          const next: RosterSort = { column, direction: active ? (direction === "asc" ? "desc" : "asc") : (column === "nickname" || column === "fid" ? "asc" : "desc") };
          setRosterSort(next);
          try { localStorage.setItem(ROSTER_SORT_KEY, JSON.stringify(next)); } catch { /* Sorting still works without storage. */ }
        }}>
          {label}<Icon size={12} aria-hidden="true" />
        </button>
      </th>
    );
  };

  return (
    <div className="page">
      <PageHeader title="Players" description={`Player roster profiles in ${selectedGroup.name}. Alliance selection in the top bar does not hide unconfirmed profiles.`} action={<button className="button button--primary" onClick={() => navigate("/admin?mode=players")}><UserPlus size={17} />Add player</button>} />
      <div className="toolbar roster-toolbar">
        <form className="filter-search" onSubmit={submit}><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ID or nickname" aria-label="Search players" /></form>
        <label className="select-control"><span>Affiliation</span><select aria-label="Roster affiliation" value={effectiveSelection} onChange={(event) => selectAffiliation(event.target.value as AffiliationSelection)}><option value="all">All players</option><option value="unconfirmed">Unconfirmed affiliation</option>{alliances.map((alliance) => <option key={alliance.id} value={`alliance:${alliance.id}`}>{alliance.alliance_type === "primary" ? "Primary alliance" : "Additional alliance"} · {alliance.name}</option>)}</select></label>
      </div>
      {error ? <ErrorState message={error} /> : !players ? <LoadingState label="Loading roster" /> : players.length === 0 ? (
        <EmptyState title={submittedQuery ? "No matching players" : "No players in this view"} description={submittedQuery ? "Try a different ID or nickname." : effectiveSelection === "unconfirmed" ? "No profiles without a confirmed primary alliance are available." : "Add the first player roster record from Administration."} action={!submittedQuery && effectiveSelection === "all" && <button className="button button--primary" onClick={() => navigate("/admin?mode=players")}>Add player</button>} />
      ) : (
        <section className="data-panel data-panel--page" aria-busy={refreshing}>
          <div className="table-wrap"><table><thead><tr>{sortHeader("nickname", "Nickname")}{sortHeader("fid", "ID")}{sortHeader("power", "Power")}{sortHeader("kills", "Kills")}{sortHeader("furnace_level", "Furnace")}{sortHeader("alliance_rank", "Rank")}<th>Alliance</th><th aria-label="Open record" /></tr></thead><tbody>{players.map((player) => <tr key={player.fid} className="clickable-row"><td><button className="table-link roster-player" onClick={() => navigate(`/players/${encodeURIComponent(player.fid)}`)}><PlayerAvatar url={player.avatar_url} /><span>{player.nickname ?? "Nickname unconfirmed"}</span></button></td><td className="mono">{player.fid}</td><td className="number-cell">{player.power?.toLocaleString() ?? "—"}</td><td className="number-cell">{player.kills?.toLocaleString() ?? "—"}</td><td className="roster-furnace"><FurnaceLevel level={player.furnace_level}/></td><td><span className={`roster-rank roster-rank--${formatAllianceRank(player.alliance_rank).toLowerCase()}`}>{formatAllianceRank(player.alliance_rank)}</span></td><td>{player.observed_alliance_name ?? player.primary_alliance_name ?? <span className="status status--draft">Unconfirmed</span>}</td><td className="row-arrow">→</td></tr>)}</tbody></table></div>
          {players.length < total ? <button className="button button--quiet" disabled={loadingMore || refreshing} onClick={() => void loadMore()}>Load more ({players.length} of {total})</button> : null}
        </section>
      )}
    </div>
  );
}
