import { AlarmState } from "@/types/alarm";

// Shared between AlarmView.tsx (Settings > Alarm) and AlarmControl.tsx (the
// global quick-access menu) so the two surfaces never drift out of sync.
export const ALARM_STATE_BADGE_CLASSES: Record<AlarmState, string> = {
  disarmed: "bg-secondary text-secondary-foreground",
  arming: "bg-yellow-500 text-white",
  exit_delay: "bg-yellow-500 text-white",
  armed_away: "bg-blue-600 text-white",
  armed_home: "bg-blue-600 text-white",
  armed_night: "bg-indigo-600 text-white",
  entry_delay: "bg-yellow-500 text-white",
  alarm: "bg-destructive text-destructive-foreground",
  alarm_memory: "bg-orange-500 text-white",
  fault: "bg-destructive text-destructive-foreground",
};
