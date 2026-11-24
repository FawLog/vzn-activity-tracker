export type EventStatus = "draft" | "published";

export interface Player {
  fid: string;
  nickname: string;
  created_at: string;
  updated_at: string;
  nickname_history?: Array<{ nickname: string; valid_from: string; valid_to: string | null }>;
  memberships?: Array<{ joined_on: string; left_on: string | null }>;
}

export interface EventRecord {
  id: string;
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
