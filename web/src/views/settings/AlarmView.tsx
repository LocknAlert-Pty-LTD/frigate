import Heading from "@/components/ui/heading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import AlarmZoneSetup from "@/views/settings/AlarmZoneSetup";
import { useTranslation } from "react-i18next";
import useSWR from "swr";
import axios from "axios";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { AlarmEvent, AlarmState, AlarmStatus, ArmedMode } from "@/types/alarm";
import { cn } from "@/lib/utils";

const STATE_BADGE_CLASSES: Record<AlarmState, string> = {
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

export default function AlarmView() {
  const { t } = useTranslation(["views/alarm"]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: status, mutate: mutateStatus } = useSWR<AlarmStatus>(
    "alarm/status",
    { refreshInterval: 5000 },
  );
  const { data: events, mutate: mutateEvents } = useSWR<AlarmEvent[]>(
    "alarm/events",
    { refreshInterval: 5000 },
  );

  const refresh = useCallback(() => {
    mutateStatus();
    mutateEvents();
  }, [mutateStatus, mutateEvents]);

  const handleError = useCallback(
    (error: unknown) => {
      const errorMessage =
        (axios.isAxiosError(error) && error.response?.data?.message) ||
        "unknown error";
      toast.error(t("toast.error", { errorMessage }), {
        position: "top-center",
      });
    },
    [t],
  );

  const arm = useCallback(
    (mode: ArmedMode) => {
      setIsSubmitting(true);
      axios
        .post("alarm/arm", { mode })
        .then((res) => {
          if (res.status === 200 && res.data.success) {
            toast.success(t("toast.armSuccess"), { position: "top-center" });
            refresh();
          } else {
            toast.error(t("toast.error", { errorMessage: res.data.message }), {
              position: "top-center",
            });
          }
        })
        .catch(handleError)
        .finally(() => setIsSubmitting(false));
    },
    [t, refresh, handleError],
  );

  const disarm = useCallback(() => {
    setIsSubmitting(true);
    axios
      .post("alarm/disarm")
      .then((res) => {
        if (res.status === 200 && res.data.success) {
          toast.success(t("toast.disarmSuccess"), { position: "top-center" });
          refresh();
        } else {
          toast.error(t("toast.error", { errorMessage: res.data.message }), {
            position: "top-center",
          });
        }
      })
      .catch(handleError)
      .finally(() => setIsSubmitting(false));
  }, [t, refresh, handleError]);

  const clear = useCallback(() => {
    setIsSubmitting(true);
    axios
      .post("alarm/clear")
      .then((res) => {
        if (res.status === 200 && res.data.success) {
          toast.success(t("toast.clearSuccess"), { position: "top-center" });
          refresh();
        } else {
          toast.error(t("toast.error", { errorMessage: res.data.message }), {
            position: "top-center",
          });
        }
      })
      .catch(handleError)
      .finally(() => setIsSubmitting(false));
  }, [t, refresh, handleError]);

  if (status === undefined) {
    return <ActivityIndicator />;
  }

  // status is null when the API returns its 400 "not enabled" body, which
  // useSWR still resolves as data since it's a 400 with a JSON body, not a
  // thrown error under the default fetcher's success-status handling.
  // Zone setup below is shown either way -- saving a zone is what enables
  // alarm in the first place, so a first-time user must be able to reach it
  // even before anything is enabled.
  const isEnabled = Boolean(status && status.state);

  const canDisarm =
    isEnabled && status.state !== "disarmed" && status.state !== "alarm_memory";
  const canClear = isEnabled && status.state === "alarm_memory";

  return (
    <div className="scrollbar-container flex size-full flex-col overflow-y-auto p-2">
      <Heading as="h4" className="mb-2">
        {t("title")}
      </Heading>
      <p className="mb-4 text-sm text-muted-foreground">{t("description")}</p>

      {!isEnabled ? (
        <div className="rounded-md border border-secondary bg-secondary/30 p-3 text-sm text-muted-foreground">
          {t("notEnabled")}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Badge className={cn(STATE_BADGE_CLASSES[status.state])}>
              {t(`state.${status.state}`)}
            </Badge>
            {status.armed_mode && (
              <Badge variant="outline">
                {t(`armedMode.${status.armed_mode}`)}
              </Badge>
            )}
            {status.reporting_healthy !== null && (
              <Badge
                variant={status.reporting_healthy ? "secondary" : "destructive"}
              >
                {t("reporting.title")}:{" "}
                {status.reporting_healthy
                  ? t("reporting.healthy")
                  : t("reporting.unhealthy")}
              </Badge>
            )}
          </div>

          {status.state === "fault" && status.fault_reason && (
            <div className="mt-3 rounded-md border border-destructive bg-destructive/10 p-3 text-sm">
              <span className="font-semibold">{t("fault.title")}: </span>
              {t("fault.reason", { reason: status.fault_reason })}
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="select"
              disabled={isSubmitting || status.state !== "disarmed"}
              onClick={() => arm("away")}
            >
              {t("actions.armAway")}
            </Button>
            <Button
              variant="select"
              disabled={isSubmitting || status.state !== "disarmed"}
              onClick={() => arm("home")}
            >
              {t("actions.armHome")}
            </Button>
            <Button
              variant="select"
              disabled={isSubmitting || status.state !== "disarmed"}
              onClick={() => arm("night")}
            >
              {t("actions.armNight")}
            </Button>
            <Button
              variant="outline"
              disabled={isSubmitting || !canDisarm}
              onClick={disarm}
            >
              {t("actions.disarm")}
            </Button>
            <Button
              variant="destructive"
              disabled={isSubmitting || !canClear}
              onClick={clear}
            >
              {t("actions.clear")}
            </Button>
          </div>

          <Separator className="my-4 bg-secondary" />

          <div className="mb-2 text-lg font-medium">{t("zones.title")}</div>
          {status.zones.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("zones.empty")}</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {status.zones.map((zone) => (
                <Badge
                  key={`${zone.camera}/${zone.zone}`}
                  variant={
                    !zone.enabled
                      ? "outline"
                      : zone.armed
                        ? "secondary"
                        : "outline"
                  }
                >
                  {zone.camera}/{zone.zone}:{" "}
                  {!zone.enabled
                    ? t("zones.disabled")
                    : zone.armed
                      ? t("zones.armed")
                      : t("zones.disarmed")}
                </Badge>
              ))}
            </div>
          )}

          <Separator className="my-4 bg-secondary" />

          <div className="mb-2 text-lg font-medium">{t("events.title")}</div>
          {!events || events.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("events.empty")}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("events.columns.time")}</TableHead>
                  <TableHead>{t("events.columns.type")}</TableHead>
                  <TableHead>{t("events.columns.camera")}</TableHead>
                  <TableHead>{t("events.columns.zone")}</TableHead>
                  <TableHead>{t("events.columns.object")}</TableHead>
                  <TableHead>{t("events.columns.confidence")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((event, index) => (
                  <TableRow key={`${event.timestamp}-${index}`}>
                    <TableCell>
                      {new Date(event.timestamp * 1000).toLocaleString()}
                    </TableCell>
                    <TableCell>{event.event_type}</TableCell>
                    <TableCell>{event.camera_id}</TableCell>
                    <TableCell>{event.zone_id ?? "-"}</TableCell>
                    <TableCell>{event.object_type ?? "-"}</TableCell>
                    <TableCell>
                      {event.confidence !== null
                        ? `${Math.round(event.confidence * 100)}%`
                        : "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}

      <Separator className="my-4 bg-secondary" />

      <AlarmZoneSetup />
    </div>
  );
}
