"""Background thread that arms/disarms the alarm system on a schedule.

Modeled on AlarmDetectionThread (frigate/alarm/detection_thread.py): a
threading.Thread polling a shared stop_event, with the actual decision
logic split into a pure, directly-testable method (_check_and_fire) rather
than living inline in run().

No new dependency for "arm at 23:00" -- Frigate has no existing cron/
scheduling library, and a plain wall-clock comparison on a ~30s poll is
simple enough that adding one isn't justified.
"""

import logging
import threading
from datetime import date, datetime
from multiprocessing.synchronize import Event as MpEvent

from frigate.alarm.audit import record_alarm_audit
from frigate.alarm.schedule import ScheduleEntry
from frigate.alarm.state import InvalidAlarmTransition
from frigate.alarm.system import AlarmSystem

logger = logging.getLogger(__name__)


class AlarmScheduler(threading.Thread):
    def __init__(
        self,
        alarm_system: AlarmSystem,
        entries: list[ScheduleEntry],
        stop_event: MpEvent,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        super().__init__(name="alarm_scheduler")
        self.alarm_system = alarm_system
        self.entries = entries
        self.stop_event = stop_event
        self.poll_interval_seconds = poll_interval_seconds
        # Dedups firing within the same day -- a 30s poll interval checks
        # each matching minute roughly twice, and a matching entry should
        # only fire once per day.
        self._fired_today: dict[int, date] = {}

    def run(self) -> None:
        while not self.stop_event.wait(self.poll_interval_seconds):
            self._check_and_fire(datetime.now())

    def _check_and_fire(self, now: datetime) -> None:
        today = now.date()
        current_time = now.strftime("%H:%M")
        weekday = now.weekday()

        for index, entry in enumerate(self.entries):
            if entry.days and weekday not in entry.days:
                continue
            if entry.time != current_time:
                continue
            if self._fired_today.get(index) == today:
                continue

            self._fired_today[index] = today
            self._fire(entry)

    def _fire(self, entry: ScheduleEntry) -> None:
        try:
            if entry.mode is None:
                self.alarm_system.disarm()
                record_alarm_audit("disarm", "schedule")
            else:
                self.alarm_system.arm(entry.mode)
                record_alarm_audit(
                    "arm", "schedule", details={"mode": entry.mode.value}
                )
        except InvalidAlarmTransition as e:
            logger.debug(
                "scheduled %s at %s skipped, state=%s",
                "disarm" if entry.mode is None else f"arm ({entry.mode.value})",
                entry.time,
                e.current.value,
            )

    def stop(self) -> None:
        self.join()
