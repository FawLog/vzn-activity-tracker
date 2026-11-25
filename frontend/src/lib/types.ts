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
  observed_alliance_name?: string | null;
  uid?: string | null;
  power?: number | null;
  kills?: number | null;
  furnace_level?: number | null;
  alliance_rank?: string | null;
  state_id?: string | null;
  avatar_url?: string | null;
  stats_observed_at?: string | null;
  stat_history?: Array<{ power: number | null; kills: number | null; furnace_level: number | null; alliance_rank: string | null; state_id: string | null; source_observed_at: string; received_at: string; alliance_id: string }>;
  membership_history?: Array<{ observed_at: string; confidence: string; alliance_name: string; alliance_tag: string }>;
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
  last_sync_at?: string | null;
  last_attempt_at?: string | null;
  last_sync_error?: string | null;
  sync_in_progress_at?: string | null;
  last_found_count?: number;
  last_added_count?: number;
  last_updated_count?: number;
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
  alliance: AllianceStatistics | null;
}

export interface AllianceStatistics {
  external_name: string | null;
  external_tag: string | null;
  state_id: string | null;
  power: number | null;
  member_count: number | null;
  power_rank: number | null;
  leader_name: string | null;
  flag_url: string | null;
  source_observed_at: string;
  received_at: string;
  power_change: number | null;
}

export interface SyncStatus {
  api_configured: boolean;
  sync_enabled: number;
  sync_interval_minutes: number | null;
  state_id: string;
  tag: string;
  last_sync_at: string | null;
  last_attempt_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  sync_in_progress_at: string | null;
  next_retry_at: string | null;
  last_found_count: number;
  last_added_count: number;
  last_updated_count: number;
  runs: Array<{ requested_at: string; completed_at: string | null; trigger_type: string; status: string; found_count: number; added_count: number; updated_count: number; message: string | null }>;
}

export interface AuditRecord {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  actor: string;
  created_at: string;
}
