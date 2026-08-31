import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import { FrigateConfig } from "@/types/frigateConfig";
import { useTranslation } from "react-i18next";
import useSWR from "swr";
import axios from "axios";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";
import { LuPlus, LuTrash2 } from "react-icons/lu";

type ArmMode = "away" | "home" | "night";
type ModeOrDisarm = ArmMode | "disarm";

type EntryDraft = {
  time: string;
  mode: ModeOrDisarm;
  days: string[];
};

const MODE_OPTIONS: ModeOrDisarm[] = ["away", "home", "night", "disarm"];
const DAY_ORDER = ["0", "1", "2", "3", "4", "5", "6"];

function toDraft(entry: {
  time: string;
  mode: ArmMode | null;
  days: number[];
}): EntryDraft {
  return {
    time: entry.time,
    mode: entry.mode ?? "disarm",
    days: entry.days.map(String),
  };
}

export default function AlarmScheduleSetup() {
  const { t } = useTranslation(["views/alarm"]);
  const { data: config, mutate: updateConfig } =
    useSWR<FrigateConfig>("config");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [entries, setEntries] = useState<EntryDraft[] | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const savedSchedule = config?.alarm.schedule;
  const currentEnabled = enabled ?? savedSchedule?.enabled ?? false;
  const currentEntries = useMemo(
    () => entries ?? (savedSchedule?.entries ?? []).map(toDraft),
    [entries, savedSchedule],
  );

  const hasChanges = enabled !== null || entries !== null;

  const updateEntry = useCallback(
    (index: number, patch: Partial<EntryDraft>) => {
      const next = currentEntries.map((entry, i) =>
        i === index ? { ...entry, ...patch } : entry,
      );
      setEntries(next);
    },
    [currentEntries],
  );

  const addEntry = useCallback(() => {
    setEntries([...currentEntries, { time: "23:00", mode: "away", days: [] }]);
  }, [currentEntries]);

  const removeEntry = useCallback(
    (index: number) => {
      setEntries(currentEntries.filter((_, i) => i !== index));
    },
    [currentEntries],
  );

  const nextAction = useMemo(() => {
    if (!currentEnabled || currentEntries.length === 0) return null;

    const now = new Date();
    let best: { entry: EntryDraft; minutesAway: number } | null = null;

    for (const entry of currentEntries) {
      const [hh, mm] = entry.time.split(":").map(Number);
      if (Number.isNaN(hh) || Number.isNaN(mm)) continue;

      for (let offset = 0; offset < 7; offset++) {
        const candidateDay = (now.getDay() + 6 + offset) % 7; // 0=Mon..6=Sun
        if (
          entry.days.length > 0 &&
          !entry.days.includes(String(candidateDay))
        ) {
          continue;
        }
        const candidate = new Date(now);
        candidate.setDate(candidate.getDate() + offset);
        candidate.setHours(hh, mm, 0, 0);
        if (candidate <= now) continue;

        const minutesAway = Math.round(
          (candidate.getTime() - now.getTime()) / 60000,
        );
        if (best === null || minutesAway < best.minutesAway) {
          best = { entry, minutesAway };
        }
        break;
      }
    }

    if (best === null) return null;
    const actionLabel =
      best.entry.mode === "disarm"
        ? t("scheduleSetup.disarmOption")
        : t(`armedMode.${best.entry.mode}`);
    return t("scheduleSetup.nextAction", {
      action: actionLabel,
      time: best.entry.time,
    });
  }, [currentEnabled, currentEntries, t]);

  const save = useCallback(() => {
    setIsSaving(true);

    axios
      .put("config/set", {
        requires_restart: 0,
        config_data: {
          alarm: {
            enabled: true,
            schedule: {
              enabled: currentEnabled,
              entries: currentEntries.map((entry) => ({
                time: entry.time,
                mode: entry.mode === "disarm" ? null : entry.mode,
                days: entry.days.map(Number),
              })),
            },
          },
        },
      })
      .then((res) => {
        if (res.status === 200) {
          toast.success(t("scheduleSetup.toast.success"), {
            position: "top-center",
          });
          setEnabled(null);
          setEntries(null);
          updateConfig();
        }
      })
      .catch((error) => {
        toast.error(
          t("scheduleSetup.toast.error", {
            errorMessage: error.response?.data?.message ?? "unknown error",
          }),
          { position: "top-center" },
        );
      })
      .finally(() => setIsSaving(false));
  }, [currentEnabled, currentEntries, t, updateConfig]);

  if (!config) {
    return <ActivityIndicator />;
  }

  return (
    <div>
      <div className="mb-2 text-lg font-medium">{t("scheduleSetup.title")}</div>
      <p className="mb-4 text-sm text-muted-foreground">
        {t("scheduleSetup.description")}
      </p>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              {t("scheduleSetup.enable")}
            </CardTitle>
            <Switch
              checked={currentEnabled}
              onCheckedChange={(checked) => setEnabled(checked)}
            />
          </div>
        </CardHeader>
        {currentEnabled && (
          <CardContent className="space-y-3">
            {nextAction && (
              <p className="text-sm text-muted-foreground">{nextAction}</p>
            )}

            {currentEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t("scheduleSetup.noEntries")}
              </p>
            ) : (
              currentEntries.map((entry, index) => (
                <div
                  key={index}
                  className="space-y-3 rounded-md border border-secondary p-3"
                >
                  <div className="flex items-end gap-3">
                    <div className="flex-1">
                      <Label className="text-xs text-muted-foreground">
                        {t("scheduleSetup.time")}
                      </Label>
                      <Input
                        type="time"
                        className="mt-1"
                        value={entry.time}
                        onChange={(e) =>
                          updateEntry(index, { time: e.target.value })
                        }
                      />
                    </div>
                    <div className="flex-1">
                      <Label className="text-xs text-muted-foreground">
                        {t("scheduleSetup.action")}
                      </Label>
                      <Select
                        value={entry.mode}
                        onValueChange={(value) =>
                          updateEntry(index, { mode: value as ModeOrDisarm })
                        }
                      >
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MODE_OPTIONS.map((mode) => (
                            <SelectItem key={mode} value={mode}>
                              {mode === "disarm"
                                ? t("scheduleSetup.disarmOption")
                                : t(`armedMode.${mode}`)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button
                      variant="destructive"
                      size="icon"
                      aria-label={t("scheduleSetup.removeEntry")}
                      onClick={() => removeEntry(index)}
                    >
                      <LuTrash2 className="size-4" />
                    </Button>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground">
                      {entry.days.length === 0 && t("scheduleSetup.everyDay")}
                    </Label>
                    <ToggleGroup
                      type="multiple"
                      variant="outline"
                      size="sm"
                      value={entry.days}
                      onValueChange={(value) =>
                        updateEntry(index, { days: value })
                      }
                      className="mt-1 justify-start"
                    >
                      {DAY_ORDER.map((day) => (
                        <ToggleGroupItem key={day} value={day} aria-label={day}>
                          {t(`scheduleSetup.days.${day}`)}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  </div>
                </div>
              ))
            )}

            <Button variant="outline" onClick={addEntry}>
              <LuPlus className="mr-1 size-4" />
              {t("scheduleSetup.addEntry")}
            </Button>
          </CardContent>
        )}
      </Card>

      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="select"
          disabled={!hasChanges || isSaving}
          onClick={save}
        >
          {isSaving
            ? t("button.saving", { ns: "common" })
            : t("scheduleSetup.save")}
        </Button>
        {hasChanges && !isSaving && (
          <span className="text-sm text-muted-foreground">
            {t("scheduleSetup.unsavedChanges")}
          </span>
        )}
      </div>
    </div>
  );
}
