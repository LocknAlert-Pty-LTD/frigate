import { useMemo } from "react";
import Chart from "react-apexcharts";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConnectionQualityIndicator } from "@/components/camera/ConnectionQualityIndicator";
import { useAutoFrigateStats } from "@/hooks/use-stats";
import useAlarmEventLog from "@/hooks/use-alarm-event-log";
import { AlarmZoneStatus } from "@/types/alarm";
import { useTheme } from "@/context/theme-provider";

type AlarmHealthDashboardProps = {
  zones: AlarmZoneStatus[];
};

export default function AlarmHealthDashboard({
  zones,
}: AlarmHealthDashboardProps) {
  const { t } = useTranslation(["views/alarm"]);
  const stats = useAutoFrigateStats();
  const { eventLog, summary, isSubmitting, setFalseAlarm } = useAlarmEventLog();
  const { theme, systemTheme } = useTheme();
  const isDark = (theme === "system" ? systemTheme : theme) === "dark";

  const alarmCameras = useMemo(
    () => Array.from(new Set(zones.map((zone) => zone.camera))),
    [zones],
  );

  const chartSeries = useMemo(() => {
    const daily = summary?.daily ?? [];
    return [
      {
        name: t("eventLog.columns.realAlarm"),
        data: daily.map((d) => d.total - d.false_alarm_count),
      },
      {
        name: t("eventLog.columns.falseAlarm"),
        data: daily.map((d) => d.false_alarm_count),
      },
    ];
  }, [summary, t]);

  const chartCategories = (summary?.daily ?? []).map((d) => d.date);

  return (
    <div>
      <div className="mb-2 text-lg font-medium">{t("cameraUptime.title")}</div>
      {alarmCameras.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t("cameraUptime.empty")}
        </p>
      ) : (
        <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3">
          {alarmCameras.map((camera) => {
            const cameraStats = stats?.cameras?.[camera];
            return (
              <Card key={camera}>
                <CardContent className="flex items-center justify-between p-3">
                  <span className="text-sm font-medium capitalize">
                    {camera.replace(/_/g, " ")}
                  </span>
                  {cameraStats ? (
                    <ConnectionQualityIndicator
                      quality={cameraStats.connection_quality}
                      expectedFps={cameraStats.expected_fps}
                      reconnects={cameraStats.reconnects_last_hour}
                      stalls={cameraStats.stalls_last_hour}
                    />
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {t("cameraUptime.noData")}
                    </span>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <div className="mb-2 mt-4 text-lg font-medium">{t("eventLog.title")}</div>
      <p className="mb-3 text-sm text-muted-foreground">
        {t("eventLog.description")}
      </p>

      {summary && (
        <div className="mb-4 flex flex-wrap gap-4">
          <Card className="flex-1">
            <CardHeader className="pb-1">
              <CardTitle className="text-sm text-muted-foreground">
                {t("eventLog.summary.total")}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold">
              {summary.total}
            </CardContent>
          </Card>
          <Card className="flex-1">
            <CardHeader className="pb-1">
              <CardTitle className="text-sm text-muted-foreground">
                {t("eventLog.summary.falseAlarms")}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold">
              {summary.false_alarm_count}
            </CardContent>
          </Card>
          <Card className="flex-1">
            <CardHeader className="pb-1">
              <CardTitle className="text-sm text-muted-foreground">
                {t("eventLog.summary.rate")}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold">
              {summary.false_alarm_rate !== null
                ? `${Math.round(summary.false_alarm_rate * 100)}%`
                : "-"}
            </CardContent>
          </Card>
        </div>
      )}

      {chartCategories.length > 0 && (
        <div className="mb-4">
          <Chart
            type="bar"
            height={220}
            options={{
              chart: {
                stacked: true,
                toolbar: { show: false },
                foreColor: isDark ? "#a1a1aa" : "#52525b",
              },
              xaxis: { categories: chartCategories },
              colors: ["var(--color-success, #22c55e)", "#ef4444"],
              legend: { show: true },
              dataLabels: { enabled: false },
            }}
            series={chartSeries}
          />
        </div>
      )}

      {!eventLog || eventLog.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("eventLog.empty")}</p>
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
              <TableHead>{t("eventLog.markFalseAlarm")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {eventLog.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell>
                  {new Date(entry.timestamp * 1000).toLocaleString()}
                </TableCell>
                <TableCell>{entry.event_type}</TableCell>
                <TableCell>{entry.camera}</TableCell>
                <TableCell>{entry.zone ?? "-"}</TableCell>
                <TableCell>{entry.object_type ?? "-"}</TableCell>
                <TableCell>
                  {entry.confidence !== null
                    ? `${Math.round(entry.confidence * 100)}%`
                    : "-"}
                </TableCell>
                <TableCell>
                  <Switch
                    checked={entry.false_alarm}
                    disabled={isSubmitting}
                    onCheckedChange={(checked) =>
                      setFalseAlarm(entry.id, checked)
                    }
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
