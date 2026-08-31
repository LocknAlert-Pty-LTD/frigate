import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TooltipPortal } from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";
import { isDesktop } from "react-device-detect";
import { LuShield } from "react-icons/lu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Drawer, DrawerContent, DrawerTrigger } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useTranslation } from "react-i18next";
import useSWR from "swr";
import { FrigateConfig } from "@/types/frigateConfig";
import useAlarmActions from "@/hooks/use-alarm-actions";
import { ALARM_STATE_BADGE_CLASSES } from "@/utils/alarmUtil";

type AlarmControlProps = {
  className?: string;
};

export default function AlarmControl({ className }: AlarmControlProps) {
  const { t } = useTranslation(["views/alarm"]);
  const { data: config } = useSWR<FrigateConfig>("config");
  const { status, isSubmitting, arm, disarm, clear, setZoneBypass } =
    useAlarmActions();

  if (!config?.alarm?.enabled) {
    return null;
  }

  const Container = isDesktop ? DropdownMenu : Drawer;
  const Trigger = isDesktop ? DropdownMenuTrigger : DrawerTrigger;
  const Content = isDesktop ? DropdownMenuContent : DrawerContent;

  const isEnabled = Boolean(status && status.state);
  const canDisarm =
    isEnabled &&
    status!.state !== "disarmed" &&
    status!.state !== "alarm_memory";
  const canClear = isEnabled && status!.state === "alarm_memory";

  return (
    <Container>
      <Tooltip>
        <Trigger asChild>
          <TooltipTrigger asChild>
            <div
              className={cn(
                "relative flex flex-col items-center justify-center",
                isDesktop
                  ? "cursor-pointer rounded-lg bg-secondary text-secondary-foreground hover:bg-muted"
                  : "text-secondary-foreground",
                className,
              )}
            >
              <LuShield className="size-5 md:m-[6px]" />
              {isEnabled && (
                <span
                  className={cn(
                    "absolute right-0 top-0 size-2 rounded-full",
                    ALARM_STATE_BADGE_CLASSES[status!.state].split(" ")[0],
                  )}
                />
              )}
            </div>
          </TooltipTrigger>
        </Trigger>
        <TooltipPortal>
          <TooltipContent side="right" sideOffset={5}>
            <p>{t("title")}</p>
          </TooltipContent>
        </TooltipPortal>
      </Tooltip>

      <Content className={cn(isDesktop ? "mr-5 w-80" : "max-h-[75dvh] p-4")}>
        <div className="scrollbar-container w-full flex-col overflow-y-auto overflow-x-hidden">
          <DropdownMenuLabel>{t("title")}</DropdownMenuLabel>
          <DropdownMenuSeparator />

          {!isEnabled ? (
            <p className="p-2 text-sm text-muted-foreground">
              {t("notEnabled")}
            </p>
          ) : (
            <div className="flex flex-col gap-3 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={cn(ALARM_STATE_BADGE_CLASSES[status!.state])}>
                  {t(`state.${status!.state}`)}
                </Badge>
                {status!.armed_mode && (
                  <Badge variant="outline">
                    {t(`armedMode.${status!.armed_mode}`)}
                  </Badge>
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="select"
                  disabled={isSubmitting || status!.state !== "disarmed"}
                  onClick={() => arm("away")}
                >
                  {t("actions.armAway")}
                </Button>
                <Button
                  size="sm"
                  variant="select"
                  disabled={isSubmitting || status!.state !== "disarmed"}
                  onClick={() => arm("home")}
                >
                  {t("actions.armHome")}
                </Button>
                <Button
                  size="sm"
                  variant="select"
                  disabled={isSubmitting || status!.state !== "disarmed"}
                  onClick={() => arm("night")}
                >
                  {t("actions.armNight")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isSubmitting || !canDisarm}
                  onClick={disarm}
                >
                  {t("actions.disarm")}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={isSubmitting || !canClear}
                  onClick={clear}
                >
                  {t("actions.clear")}
                </Button>
              </div>

              {status!.zones.length > 0 && (
                <>
                  <DropdownMenuSeparator />
                  <div className="text-xs font-medium text-muted-foreground">
                    {t("zones.title")}
                  </div>
                  {status!.zones.map((zone) => (
                    <div
                      key={`${zone.camera}/${zone.zone}`}
                      className="flex items-center justify-between gap-2 text-sm"
                    >
                      <span className="truncate">
                        {zone.camera}/{zone.zone}
                      </span>
                      {zone.enabled && (
                        <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                          {t("zones.bypass")}
                          <Switch
                            checked={zone.bypassed}
                            disabled={isSubmitting}
                            onCheckedChange={(checked) =>
                              setZoneBypass(zone.camera, zone.zone, checked)
                            }
                          />
                        </label>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </Content>
    </Container>
  );
}
