import { useCallback, useState } from "react";
import useSWR from "swr";
import axios from "axios";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import {
  AlarmAuditLogEntry,
  AlarmEvent,
  AlarmStatus,
  ArmedMode,
} from "@/types/alarm";

/**
 * Shared alarm arm/disarm/clear/bypass mutations, backed by the same SWR
 * cache keys ("alarm/status"/"alarm/events") everywhere it's used -- so
 * AlarmView.tsx and AlarmControl.tsx (the quick-access menu) both stay in
 * sync automatically after either one mutates, with no extra wiring.
 */
export default function useAlarmActions() {
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
  const { data: auditLog, mutate: mutateAuditLog } = useSWR<
    AlarmAuditLogEntry[]
  >("alarm/audit", { refreshInterval: 5000 });

  const refresh = useCallback(() => {
    mutateStatus();
    mutateEvents();
    mutateAuditLog();
  }, [mutateStatus, mutateEvents, mutateAuditLog]);

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

  const setZoneBypass = useCallback(
    (camera: string, zone: string, bypassed: boolean) => {
      setIsSubmitting(true);
      axios
        .post(`alarm/zones/${camera}/${zone}/bypass`, { bypassed })
        .then((res) => {
          if (res.status === 200 && res.data.success) {
            toast.success(
              bypassed ? t("toast.bypassSuccess") : t("toast.unbypassSuccess"),
              { position: "top-center" },
            );
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

  return {
    status,
    events,
    auditLog,
    isSubmitting,
    arm,
    disarm,
    clear,
    setZoneBypass,
  };
}
