/**
 * Types for the alarm engine
 */

export type AlarmState =
  | "disarmed"
  | "arming"
  | "exit_delay"
  | "armed_away"
  | "armed_stay"
  | "entry_delay"
  | "alarm"
  | "alarm_memory"
  | "fault";

export type ArmedMode = "away" | "stay";

export interface AlarmZoneStatus {
  camera: string;
  zone: string;
  enabled: boolean;
  armed: boolean;
}

export interface AlarmStatus {
  state: AlarmState;
  armed_mode: ArmedMode | null;
  is_alarm_active: boolean;
  is_alarm_memory: boolean;
  fault_reason: string | null;
  last_transition: string;
  reporting_healthy: boolean | null;
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
}
