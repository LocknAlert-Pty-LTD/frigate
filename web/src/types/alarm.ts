/**
 * Types for the alarm engine
 */

export type AlarmState =
  | "disarmed"
  | "arming"
  | "exit_delay"
  | "armed_away"
  | "armed_home"
  | "armed_night"
  | "entry_delay"
  | "alarm"
  | "alarm_memory"
  | "fault";

// "night" is surfaced to users as "Sleep" -- same concept, Home Assistant's
// literal name for the mode.
export type ArmedMode = "away" | "home" | "night";

export interface AlarmZoneStatus {
  camera: string;
  zone: string;
  enabled: boolean;
  armed: boolean;
  bypassed: boolean;
}

export interface AlarmStatus {
  state: AlarmState;
  armed_mode: ArmedMode | null;
  is_alarm_active: boolean;
  is_alarm_memory: boolean;
  fault_reason: string | null;
  last_transition: string;
  reporting_healthy: boolean | null;
  whatsapp_healthy: boolean | null;
  zones: AlarmZoneStatus[];
}

export interface AlarmEvent {
  event_type: string;
  camera_id: string;
  timestamp: number;
  zone_id: string | null;
  object_type: string | null;
  confidence: number | null;
  source: string;
  message: string | null;
  // The underlying Frigate tracked-object/Event id, used to look up the
  // cross-camera trail (see useAlarmTrail). Null for non-detection events
  // (arm/disarm/fault/etc).
  object_id: string | null;
}

// "named" comes from face recognition matching the same person's name on
// another camera; "visual" is the semantic-search appearance-similarity
// fallback for unidentified people. Either signal is opt-in on the
// backend, so this can be empty even during a real incident.
export interface AlarmTrailMatch {
  camera: string;
  event_id: string;
  timestamp: number;
  thumbnail: string;
  match_type: "named" | "visual";
  label: string | null;
  score: number | null;
}

export interface AlarmTrail {
  matches: AlarmTrailMatch[];
}

// "action" values match the DB (arm/disarm/clear/bypass/unbypass);
// "source" is where the action originated (api/mqtt).
export interface AlarmAuditLogEntry {
  timestamp: number;
  action: "arm" | "disarm" | "clear" | "bypass" | "unbypass" | "false_alarm";
  source: "api" | "mqtt" | "schedule";
  actor: string | null;
  camera: string | null;
  zone: string | null;
  details: Record<string, unknown> | null;
}

// Persisted, restart-surviving counterpart to AlarmEvent (which is
// in-memory only, most-recent-100, lost on restart) -- used by the health
// dashboard's false-alarm rate.
export interface AlarmEventLogEntry {
  id: number;
  timestamp: number;
  event_type: string;
  camera: string;
  zone: string | null;
  object_type: string | null;
  confidence: number | null;
  false_alarm: boolean;
}

export interface AlarmEventLogDay {
  date: string;
  total: number;
  false_alarm_count: number;
}

export interface AlarmEventLogSummary {
  total: number;
  false_alarm_count: number;
  false_alarm_rate: number | null;
  daily: AlarmEventLogDay[];
}
