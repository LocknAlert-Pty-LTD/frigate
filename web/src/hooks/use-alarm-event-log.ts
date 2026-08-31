import { useCallback, useState } from "react";
import useSWR from "swr";
import axios from "axios";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { AlarmEventLogEntry, AlarmEventLogSummary } from "@/types/alarm";

/**
 * Persisted alarm event history + false-alarm marking for the health
 * dashboard. Separate SWR cache keys from useAlarmActions' "alarm/events"
 * (the in-memory, most-recent-100 feed) -- this is the historical,
 * restart-surviving, annotatable counterpart.
 */
export default function useAlarmEventLog() {
  const { t } = useTranslation(["views/alarm"]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: eventLog, mutate: mutateEventLog } = useSWR<
    AlarmEventLogEntry[]
  >("alarm/event_log", { refreshInterval: 30000 });
  const { data: summary, mutate: mutateSummary } = useSWR<AlarmEventLogSummary>(
    "alarm/event_log/summary",
    {
      refreshInterval: 30000,
    },
  );

  const setFalseAlarm = useCallback(
    (id: number, falseAlarm: boolean) => {
      setIsSubmitting(true);
      axios
        .post(`alarm/event_log/${id}/false_alarm`, { false_alarm: falseAlarm })
        .then((res) => {
          if (res.status === 200 && res.data.success) {
            toast.success(
              falseAlarm
                ? t("eventLog.toast.markedSuccess")
                : t("eventLog.toast.unmarkedSuccess"),
              { position: "top-center" },
            );
            mutateEventLog();
            mutateSummary();
          } else {
            toast.error(t("toast.error", { errorMessage: res.data.message }), {
              position: "top-center",
            });
          }
        })
        .catch((error) => {
          const errorMessage =
            (axios.isAxiosError(error) && error.response?.data?.message) ||
            "unknown error";
          toast.error(t("toast.error", { errorMessage }), {
            position: "top-center",
          });
        })
        .finally(() => setIsSubmitting(false));
    },
    [t, mutateEventLog, mutateSummary],
  );

  return { eventLog, summary, isSubmitting, setFalseAlarm };
}
