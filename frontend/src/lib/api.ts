import type { Alliance, AllianceGroup, AuditRecord, EventRecord, OverviewData, Player } from "./types";

interface ErrorEnvelope {
  error?: { message?: string };
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(value: string | null): void {
  csrfToken = value;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrfToken && options.method && options.method !== "GET") {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new ApiRequestError(payload.error?.message ?? "Request failed.", response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  csrf: () => request<{ csrf_token: string; authenticated: boolean }>("/api/v1/auth/csrf"),
  login: (password: string) =>
    request<{ csrf_token: string; authenticated: true }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  onboarding: () => request<{ required: boolean; group_count: number; unassigned_legacy_events: number }>("/api/v1/onboarding"),
  completeOnboarding: (payload: GroupPayload) => request<AllianceGroup>("/api/v1/onboarding/groups", { method: "POST", body: JSON.stringify(payload) }),
  groups: () => request<{ items: AllianceGroup[] }>("/api/v1/groups"),
  createGroup: (payload: GroupPayload) => request<AllianceGroup>("/api/v1/groups", { method: "POST", body: JSON.stringify(payload) }),
  updateGroup: (groupId: string, payload: Partial<GroupUpdatePayload>) => request<AllianceGroup>(`/api/v1/groups/${encodeURIComponent(groupId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  alliances: (groupId: string) => request<{ items: Alliance[] }>(`/api/v1/groups/${encodeURIComponent(groupId)}/alliances`),
  createAlliance: (groupId: string, payload: AlliancePayload) => request<Alliance>(`/api/v1/groups/${encodeURIComponent(groupId)}/alliances`, { method: "POST", body: JSON.stringify(payload) }),
  updateAlliance: (groupId: string, allianceId: string, payload: Partial<AllianceUpdatePayload>) => request<Alliance>(`/api/v1/groups/${encodeURIComponent(groupId)}/alliances/${encodeURIComponent(allianceId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  overview: (groupId: string) => request<OverviewData>(`/api/v1/groups/${encodeURIComponent(groupId)}/overview`),
  players: (groupId: string, query = "", sort = "nickname", direction = "asc", filter: PlayerAffiliationFilter = { mode: "all" }) =>
    request<{ items: Player[] }>(
      `/api/v1/groups/${encodeURIComponent(groupId)}/players?q=${encodeURIComponent(query)}&sort=${encodeURIComponent(sort)}&direction=${direction}&affiliation=${filter.mode}${filter.mode === "alliance" ? `&alliance_id=${encodeURIComponent(filter.allianceId)}` : ""}`,
    ),
  player: (groupId: string, fid: string) => request<Player>(`/api/v1/groups/${encodeURIComponent(groupId)}/players/${encodeURIComponent(fid)}`),
  createPlayer: (groupId: string, payload: { fid: string; nickname: string }) =>
    request<Player>(`/api/v1/groups/${encodeURIComponent(groupId)}/players`, { method: "POST", body: JSON.stringify(payload) }),
  events: (groupId: string, allianceId: string, sort = "occurred_on", direction = "desc") =>
    request<{ items: EventRecord[] }>(
      `/api/v1/groups/${encodeURIComponent(groupId)}/alliances/${encodeURIComponent(allianceId)}/events?sort=${encodeURIComponent(sort)}&direction=${direction}`,
    ),
  event: (groupId: string, id: string) => request<EventRecord>(`/api/v1/groups/${encodeURIComponent(groupId)}/events/${encodeURIComponent(id)}`),
  createEvent: (groupId: string, allianceId: string, payload: { event_type: string; occurred_on: string; status: string }) =>
    request<EventRecord>(`/api/v1/groups/${encodeURIComponent(groupId)}/alliances/${encodeURIComponent(allianceId)}/events`, { method: "POST", body: JSON.stringify(payload) }),
  rankings: (groupId: string) =>
    request<{ categories: Array<{ id: string; status: string }>; message: string }>(`/api/v1/groups/${encodeURIComponent(groupId)}/rankings`),
  audit: () => request<{ items: AuditRecord[] }>("/api/v1/admin/audit"),
};

export interface AlliancePayload { name: string; tag: string; state_id: string; }
export type PlayerAffiliationFilter =
  | { mode: "all" }
  | { mode: "unconfirmed" }
  | { mode: "alliance"; allianceId: string };
export interface AllianceUpdatePayload extends AlliancePayload { status: "active" | "archived"; confirm_archive: boolean; }
export interface GroupPayload {
  name: string;
  discord_server_id?: string | null;
  combined_statistics: boolean;
  primary_alliance_name: string;
  primary_alliance_tag: string;
  primary_alliance_state_id: string;
  assign_legacy_events: boolean;
  confirm_legacy_assignment: boolean;
}
export interface GroupUpdatePayload { name: string; discord_server_id: string | null; combined_statistics: boolean; status: "active" | "archived"; confirm_archive: boolean; }
