import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import { FrigateConfig } from "@/types/frigateConfig";
import { useTranslation } from "react-i18next";
import useSWR from "swr";
import axios from "axios";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

type ArmMode = "away" | "home" | "night";

type ZoneDraft = {
  enabled: boolean;
  objects: string[];
  armModes: ArmMode[];
  delay: number;
  verificationSeconds: number;
};

const ARM_MODES: ArmMode[] = ["away", "home", "night"];

export default function AlarmZoneSetup() {
  const { t } = useTranslation(["views/alarm"]);
  const { data: config, mutate: updateConfig } =
    useSWR<FrigateConfig>("config");
  const [drafts, setDrafts] = useState<Record<string, ZoneDraft>>({});
  const [isSaving, setIsSaving] = useState(false);

  const draftFor = useCallback(
    (camera: string, zone: string): ZoneDraft => {
      const key = `${camera}__${zone}`;
      if (drafts[key]) {
        return drafts[key];
      }

      const existing = config?.cameras[camera]?.alarm?.zones?.[zone];
      return {
        enabled: existing?.enabled ?? false,
        objects: existing?.objects ?? [],
        armModes: (existing?.arm_modes as ArmMode[] | undefined) ?? ARM_MODES,
        delay: existing?.delay ?? 0,
        verificationSeconds: existing?.verification_seconds ?? 0,
      };
    },
    [config, drafts],
  );

  const updateDraft = useCallback(
    (camera: string, zone: string, patch: Partial<ZoneDraft>) => {
      const key = `${camera}__${zone}`;
      setDrafts((prev) => ({
        ...prev,
        [key]: { ...draftFor(camera, zone), ...patch },
      }));
    },
    [draftFor],
  );

  const hasChanges = Object.keys(drafts).length > 0;

  const camerasWithZones = useMemo(() => {
    if (!config) return [];
    return Object.entries(config.cameras).filter(
      ([, camera]) => Object.keys(camera.zones ?? {}).length > 0,
    );
  }, [config]);

  const save = useCallback(() => {
    setIsSaving(true);

    const camerasPatch: Record<
      string,
      { alarm: { enabled: boolean; zones: Record<string, unknown> } }
    > = {};
    for (const [key, draft] of Object.entries(drafts)) {
      const [camera, zone] = key.split("__");
      if (!camerasPatch[camera]) {
        camerasPatch[camera] = { alarm: { enabled: true, zones: {} } };
      }
      camerasPatch[camera].alarm.zones[zone] = {
        enabled: draft.enabled,
        objects: draft.objects,
        arm_modes: draft.armModes,
        delay: draft.delay,
        verification_seconds: draft.verificationSeconds,
      };
    }

    axios
      .put("config/set", {
        requires_restart: 0,
        config_data: { alarm: { enabled: true }, cameras: camerasPatch },
      })
      .then((res) => {
        if (res.status === 200) {
          toast.success(t("zoneSetup.toast.success"), {
            position: "top-center",
          });
          setDrafts({});
          updateConfig();
        }
      })
      .catch((error) => {
        toast.error(
          t("zoneSetup.toast.error", {
            errorMessage: error.response?.data?.message ?? "unknown error",
          }),
          { position: "top-center" },
        );
      })
      .finally(() => setIsSaving(false));
  }, [drafts, t, updateConfig]);

  if (!config) {
    return <ActivityIndicator />;
  }

  return (
    <div>
      <div className="mb-2 text-lg font-medium">{t("zoneSetup.title")}</div>
      <p className="mb-4 text-sm text-muted-foreground">
        {t("zoneSetup.description")}
      </p>

      {camerasWithZones.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t("zoneSetup.noZonesAnywhere")}
        </p>
      ) : (
        <div className="space-y-3">
          {camerasWithZones.map(([cameraName, camera]) => (
            <Card key={cameraName}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base capitalize">
                  {camera.friendly_name || cameraName}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {Object.keys(camera.zones).map((zoneName) => {
                  const draft = draftFor(cameraName, zoneName);
                  const inputId = `${cameraName}-${zoneName}`;

                  return (
                    <div
                      key={zoneName}
                      className="rounded-md border border-secondary p-3"
                    >
                      <div className="flex items-center justify-between">
                        <Label
                          htmlFor={`zone-toggle-${inputId}`}
                          className="text-sm font-medium capitalize"
                        >
                          {zoneName.replace(/_/g, " ")}
                        </Label>
                        <Switch
                          id={`zone-toggle-${inputId}`}
                          checked={draft.enabled}
                          onCheckedChange={(checked) =>
                            updateDraft(cameraName, zoneName, {
                              enabled: checked,
                            })
                          }
                        />
                      </div>

                      {draft.enabled && (
                        <div className="mt-3 space-y-3">
                          <div>
                            <Label className="text-xs text-muted-foreground">
                              {t("zoneSetup.objects")}
                            </Label>
                            <ToggleGroup
                              type="multiple"
                              variant="outline"
                              size="sm"
                              value={draft.objects}
                              onValueChange={(value) =>
                                updateDraft(cameraName, zoneName, {
                                  objects: value,
                                })
                              }
                              className="mt-1 flex-wrap justify-start"
                            >
                              {camera.objects.track.map((obj) => (
                                <ToggleGroupItem
                                  key={obj}
                                  value={obj}
                                  className="capitalize"
                                  aria-label={obj}
                                >
                                  {obj}
                                </ToggleGroupItem>
                              ))}
                            </ToggleGroup>
                          </div>

                          <div>
                            <Label className="text-xs text-muted-foreground">
                              {t("zoneSetup.activeWhen")}
                            </Label>
                            <ToggleGroup
                              type="multiple"
                              variant="outline"
                              size="sm"
                              value={draft.armModes}
                              onValueChange={(value) =>
                                updateDraft(cameraName, zoneName, {
                                  armModes: value as ArmMode[],
                                })
                              }
                              className="mt-1 justify-start"
                            >
                              {ARM_MODES.map((mode) => (
                                <ToggleGroupItem
                                  key={mode}
                                  value={mode}
                                  aria-label={mode}
                                >
                                  {t(`armedMode.${mode}`)}
                                </ToggleGroupItem>
                              ))}
                            </ToggleGroup>
                          </div>

                          <div className="flex gap-4">
                            <div className="flex-1">
                              <Label
                                htmlFor={`delay-${inputId}`}
                                className="text-xs text-muted-foreground"
                              >
                                {t("zoneSetup.entryDelay")}
                              </Label>
                              <Input
                                id={`delay-${inputId}`}
                                type="number"
                                min={0}
                                className="mt-1"
                                value={draft.delay}
                                onChange={(e) =>
                                  updateDraft(cameraName, zoneName, {
                                    delay: Math.max(0, Number(e.target.value)),
                                  })
                                }
                              />
                            </div>
                            <div className="flex-1">
                              <Label
                                htmlFor={`verify-${inputId}`}
                                className="text-xs text-muted-foreground"
                              >
                                {t("zoneSetup.verification")}
                              </Label>
                              <Input
                                id={`verify-${inputId}`}
                                type="number"
                                min={0}
                                className="mt-1"
                                value={draft.verificationSeconds}
                                onChange={(e) =>
                                  updateDraft(cameraName, zoneName, {
                                    verificationSeconds: Math.max(
                                      0,
                                      Number(e.target.value),
                                    ),
                                  })
                                }
                              />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="select"
          disabled={!hasChanges || isSaving}
          onClick={save}
        >
          {isSaving
            ? t("button.saving", { ns: "common" })
            : t("zoneSetup.save")}
        </Button>
        {hasChanges && !isSaving && (
          <span className="text-sm text-muted-foreground">
            {t("zoneSetup.unsavedChanges")}
          </span>
        )}
      </div>
    </div>
  );
}
