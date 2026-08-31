import Heading from "@/components/ui/heading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
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
import AlarmScheduleSetup from "@/views/settings/AlarmScheduleSetup";
import AlarmHealthDashboard from "@/views/settings/AlarmHealthDashboard";
import { useTranslation } from "react-i18next";
import useAlarmActions from "@/hooks/use-alarm-actions";
import { ALARM_STATE_BADGE_CLASSES } from "@/utils/alarmUtil";
import { cn } from "@/lib/utils";

export default function AlarmView() {
  const { t } = useTranslation(["views/alarm"]);
  const {
    status,
    events,
    auditLog,
    isSubmitting,
    arm,
    disarm,
    clear,
    setZoneBypass,
  } = useAlarmActions();

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
            <Badge className={cn(ALARM_STATE_BADGE_CLASSES[status.state])}>
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
            {status.whatsapp_healthy !== null && (
              <Badge
                variant={status.whatsapp_healthy ? "secondary" : "destructive"}
              >
                {t("whatsapp.title")}:{" "}
                {status.whatsapp_healthy
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
            <div className="flex flex-col gap-2">
              {status.zones.map((zone) => (
                <div
                  key={`${zone.camera}/${zone.zone}`}
                  className="flex flex-wrap items-center gap-2"
                >
                  <Badge
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
                      : zone.bypassed
                        ? t("zones.bypassed")
                        : zone.armed
                          ? t("zones.armed")
                          : t("zones.disarmed")}
                  </Badge>
                  {zone.enabled && (
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Switch
                        checked={zone.bypassed}
                        disabled={isSubmitting}
                        onCheckedChange={(checked) =>
                          setZoneBypass(zone.camera, zone.zone, checked)
                        }
                      />
                      {t("zones.bypass")}
                    </label>
                  )}
                </div>
              ))}
            </div>
          )}

          <Separator className="my-4 bg-secondary" />

          <AlarmHealthDashboard zones={status.zones} />

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

          <Separator className="my-4 bg-secondary" />

          <div className="mb-2 text-lg font-medium">{t("audit.title")}</div>
          {!auditLog || auditLog.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("audit.empty")}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("audit.columns.time")}</TableHead>
                  <TableHead>{t("audit.columns.action")}</TableHead>
                  <TableHead>{t("audit.columns.source")}</TableHead>
                  <TableHead>{t("audit.columns.actor")}</TableHead>
                  <TableHead>{t("audit.columns.zone")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditLog.map((entry, index) => (
                  <TableRow key={`${entry.timestamp}-${index}`}>
                    <TableCell>
                      {new Date(entry.timestamp * 1000).toLocaleString()}
                    </TableCell>
                    <TableCell>{t(`audit.actions.${entry.action}`)}</TableCell>
                    <TableCell>{t(`audit.sources.${entry.source}`)}</TableCell>
                    <TableCell>{entry.actor ?? "-"}</TableCell>
                    <TableCell>
                      {entry.camera && entry.zone
                        ? `${entry.camera}/${entry.zone}`
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

      <Separator className="my-4 bg-secondary" />

      <AlarmScheduleSetup />
    </div>
  );
}
