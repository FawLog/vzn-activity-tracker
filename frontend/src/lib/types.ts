export type EventStatus = "draft" | "published";

export interface Player {
  fid: string;
  nickname: string | null;
  created_at: string;
  updated_at: string;
  nickname_history?: Array<{ nickname: string; valid_from: string; valid_to: string | null }>;
  group_status?: "unconfirmed" | "active" | "archived";
  primary_alliance_id?: string | null;
  primary_alliance_name?: string | null;
}

export interface AllianceGroup {
  id: string;
  name: string;
  discord_server_id: string | null;
  combined_statistics: number;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  alliance_count: number;
  primary_count: number;
}

export interface Alliance {
  id: string;
  group_id: string;
  name: string;
  tag: string;
  state_id: string;
  alliance_type: "primary" | "additional";
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  sync_enabled?: number;
  sync_interval_minutes?: number | null;
  last_sync_status?: string | null;
}

export interface EventRecord {
  id: string;
  alliance_id: string;
  alliance_name?: string;
  event_type: string;
  occurred_on: string;
  status: EventStatus;
  participant_count?: number;
  created_at: string;
  updated_at: string;
  participants?: Array<{
    fid: string;
    nickname: string;
    presence_status: "confirmed_present" | "confirmed_absent" | "excused" | "unknown";
    roster_role: "main" | "substitute" | "unregistered" | null;
    raw_points: number | null;
    source_complete: number;
  }>;
}

export interface OverviewData {
  players: number;
  events: number;
  published_events: number;
  recent_events: EventRecord[];
}

export interface AuditRecord {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  actor: string;
  created_at: string;
}
