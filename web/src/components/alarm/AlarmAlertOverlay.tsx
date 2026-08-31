import { useAlarmEvents, useAlarmState } from "@/api/ws";
import LivePlayer from "@/components/player/LivePlayer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import useCameraLiveMode from "@/hooks/use-camera-live-mode";
import { useCameraFriendlyName } from "@/hooks/use-camera-friendly-name";
import useAlarmTrail from "@/hooks/use-alarm-trail";
import { AlarmEvent } from "@/types/alarm";
import { CameraConfig, FrigateConfig } from "@/types/frigateConfig";
import { LivePlayerMode } from "@/types/live";
import { ALARM_STATE_BADGE_CLASSES } from "@/utils/alarmUtil";
import { cn } from "@/lib/utils";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LuX } from "react-icons/lu";
import useSWR from "swr";

// Avoids an unbounded grid if an unusual number of zones fire at once;
// anything beyond this is still recorded (alarm/events, the audit log)
// just not tiled here.
const MAX_VISIBLE_CAMERAS = 4;

export default function AlarmAlertOverlay() {
  const { t } = useTranslation(["views/alarm"]);
  const { data: config } = useSWR<FrigateConfig>("config");

  const { payload: event } = useAlarmEvents();
  const { payload: status } = useAlarmState();

  // Keyed by camera_id so a second camera joining the same incident adds a
  // tile instead of replacing the first one -- the whole point of this
  // part. Only accumulates events received while this component is
  // mounted; it does not reconstruct an already-in-progress incident's
  // full camera set on a fresh page load (see AGENTS.md roadmap part 2).
  const [activeEvents, setActiveEvents] = useState<Map<string, AlarmEvent>>(
    new Map(),
  );
  const [dismissedAt, setDismissedAt] = useState<number | undefined>();

  useEffect(() => {
    if (!event) return;
    setActiveEvents((prev) => {
      if (prev.get(event.camera_id)?.timestamp === event.timestamp) {
        return prev;
      }
      return new Map(prev).set(event.camera_id, event);
    });
    // A genuinely new camera joining the incident should re-surface the
    // panel even if it was dismissed -- a human should see it.
    setDismissedAt(undefined);
  }, [event]);

  // Clears once the alarm is no longer active (disarmed/cleared), matching
  // a real panel rather than leaving a stale alert on screen forever.
  useEffect(() => {
    if (
      status &&
      !status.is_alarm_active &&
      status.state !== "entry_delay" &&
      status.state !== "exit_delay"
    ) {
      setActiveEvents(new Map());
      setDismissedAt(undefined);
    }
  }, [status]);

  const sortedEvents = useMemo(
    () =>
      Array.from(activeEvents.values()).sort(
        (a, b) => b.timestamp - a.timestamp,
      ),
    [activeEvents],
  );
  const visibleEvents = sortedEvents.slice(0, MAX_VISIBLE_CAMERAS);
  const overflowCount = sortedEvents.length - visibleEvents.length;

  const cameraConfigs = useMemo(
    () =>
      config
        ? visibleEvents
            .map((e) => config.cameras[e.camera_id])
            .filter((c): c is CameraConfig => Boolean(c))
        : [],
    [config, visibleEvents],
  );
  const { preferredLiveModes } = useCameraLiveMode(cameraConfigs, true);

  if (visibleEvents.length === 0 || cameraConfigs.length === 0 || dismissedAt) {
    return null;
  }

  const escalated = status?.is_alarm_active ?? false;
  const isMulti = cameraConfigs.length > 1;

  return (
    <Card
      className={cn(
        "fixed bottom-4 right-4 z-50 shadow-2xl transition-colors",
        isMulti ? "w-[calc(100vw-2rem)] max-w-[720px]" : "w-[380px]",
        escalated
          ? "border-2 border-destructive"
          : "border-2 border-yellow-500",
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            {t("alert.incidentTitle")}
            <Badge
              variant={escalated ? "destructive" : "secondary"}
              className={cn(
                !escalated && ALARM_STATE_BADGE_CLASSES[status!.state],
              )}
            >
              {escalated ? t("state.alarm") : t(`state.${status!.state}`)}
            </Badge>
            {overflowCount > 0 && (
              <Badge variant="outline">
                {t("alert.more", { count: overflowCount })}
              </Badge>
            )}
          </CardTitle>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          onClick={() => setDismissedAt(Date.now())}
        >
          <LuX className="size-4" />
        </Button>
      </CardHeader>
      <CardContent
        className={cn(
          "pb-4",
          isMulti ? "grid grid-cols-1 gap-3 sm:grid-cols-2" : "",
        )}
      >
        {visibleEvents.map((e) => (
          <AlarmCameraTile
            key={e.camera_id}
            event={e}
            cameraConfig={config!.cameras[e.camera_id]}
            preferredLiveMode={preferredLiveModes[e.camera_id] ?? "mse"}
          />
        ))}
      </CardContent>
    </Card>
  );
}

type AlarmCameraTileProps = {
  event: AlarmEvent;
  cameraConfig: CameraConfig;
  preferredLiveMode: LivePlayerMode;
};

function AlarmCameraTile({
  event,
  cameraConfig,
  preferredLiveMode,
}: AlarmCameraTileProps) {
  const { t } = useTranslation(["views/alarm"]);
  const navigate = useNavigate();
  const friendlyName = useCameraFriendlyName(cameraConfig);
  const streamName = useMemo(
    () => Object.values(cameraConfig.live.streams || {})[0] || "",
    [cameraConfig],
  );
  const { matches: trailMatches } = useAlarmTrail(event.object_id);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="overflow-hidden rounded-md bg-black">
        <LivePlayer
          cameraConfig={cameraConfig}
          streamName={streamName}
          preferredLiveMode={preferredLiveMode}
          useWebGL={false}
          playInBackground={false}
          autoLive
          showStillWithoutActivity={false}
          className="aspect-video"
        />
      </div>
      <div className="text-sm">
        <div className="font-medium">{friendlyName}</div>
        <div className="text-xs text-muted-foreground">
          {event.zone_id && `${t("events.columns.zone")}: ${event.zone_id}`}
          {event.object_type && (
            <>
              {event.zone_id ? " · " : ""}
              {event.object_type}
              {event.confidence != null &&
                ` (${Math.round(event.confidence * 100)}%)`}
            </>
          )}
        </div>
      </div>
      {trailMatches.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-xs text-muted-foreground">
            {t("alert.trail.title")}
          </div>
          <div className="flex flex-wrap gap-1">
            {trailMatches.map((m) => (
              <Badge key={m.event_id} variant="outline" className="text-xs">
                {m.match_type === "named"
                  ? t("alert.trail.namedMatch", {
                      camera: m.camera,
                      label: m.label,
                    })
                  : t("alert.trail.visualMatch", { camera: m.camera })}
              </Badge>
            ))}
          </div>
        </div>
      )}
      <Button
        size="sm"
        variant="outline"
        onClick={() => navigate(`/#${event.camera_id}`)}
      >
        {t("alert.view")}
      </Button>
    </div>
  );
}
