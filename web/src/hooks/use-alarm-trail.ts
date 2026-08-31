import useSWR from "swr";
import { AlarmTrail } from "@/types/alarm";

/**
 * Cross-camera "also seen" lookup for one alarm-triggering detection.
 * Mirrors useAlarmEventLog's plain-SWR-cache pattern. Fetch is skipped
 * (SWR key null) until an objectId is available -- most non-detection
 * alarm events (arm/disarm/fault) never have one.
 */
export default function useAlarmTrail(
  objectId: string | null | undefined,
  windowSeconds = 120,
) {
  const { data: trail } = useSWR<AlarmTrail>(
    objectId ? `alarm/trail/${objectId}?window_seconds=${windowSeconds}` : null,
    { refreshInterval: 10000 },
  );

  return { matches: trail?.matches ?? [] };
}
