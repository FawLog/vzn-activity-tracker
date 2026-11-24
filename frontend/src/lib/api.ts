import type { AuditRecord, EventRecord, OverviewData, Player } from "./types";

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
  overview: () => request<OverviewData>("/api/v1/overview"),
  players: (query = "", sort = "nickname", direction = "asc") =>
    request<{ items: Player[] }>(
      `/api/v1/players?q=${encodeURIComponent(query)}&sort=${encodeURIComponent(sort)}&direction=${direction}`,
    ),
  player: (fid: string) => request<Player>(`/api/v1/players/${encodeURIComponent(fid)}`),
  createPlayer: (payload: { fid: string; nickname: string }) =>
    request<Player>("/api/v1/players", { method: "POST", body: JSON.stringify(payload) }),
  events: (sort = "occurred_on", direction = "desc") =>
    request<{ items: EventRecord[] }>(
      `/api/v1/events?sort=${encodeURIComponent(sort)}&direction=${direction}`,
    ),
  event: (id: string) => request<EventRecord>(`/api/v1/events/${encodeURIComponent(id)}`),
  createEvent: (payload: { event_type: string; occurred_on: string; status: string }) =>
    request<EventRecord>("/api/v1/events", { method: "POST", body: JSON.stringify(payload) }),
  rankings: () =>
    request<{ categories: Array<{ id: string; status: string }>; message: string }>("/api/v1/rankings"),
  audit: () => request<{ items: AuditRecord[] }>("/api/v1/admin/audit"),
};
