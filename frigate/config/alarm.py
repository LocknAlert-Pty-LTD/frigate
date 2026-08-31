"""Global alarm engine configuration."""

from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from frigate.alarm.notify_whatsapp import WhatsAppNotifyConfig
from frigate.alarm.schedule import ScheduleEntry
from frigate.alarm.state import ArmedMode

from .base import FrigateBaseModel

__all__ = [
    "AlarmConfig",
    "AlarmReportingConfig",
    "AlarmReportingProtocol",
    "AlarmScheduleConfig",
    "AlarmScheduleEntryConfig",
    "AlarmWhatsAppConfig",
]


class AlarmReportingProtocol(str, Enum):
    none = "none"
    sia_dc09 = "sia_dc09"
    contact_id = "contact_id"


class AlarmReportingConfig(FrigateBaseModel):
    protocol: AlarmReportingProtocol = Field(
        default=AlarmReportingProtocol.none,
        title="Reporting protocol",
        description="Central station reporting protocol. sia_dc09 is an unverified best-effort implementation (no spec was available); contact_id's event codes are verified against a real reference. none disables reporting.",
    )
    host: str | None = Field(
        default=None,
        title="Receiver host",
        description="Central monitoring station receiver hostname or IP.",
    )
    port: int | None = Field(
        default=None,
        gt=0,
        le=65535,
        title="Receiver port",
        description="Central monitoring station receiver port.",
    )
    account: str | None = Field(
        default=None,
        title="Account number",
        description="Account number registered with the central monitoring station.",
    )
    timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        title="Connection timeout",
        description="Timeout (seconds) for connecting to and sending to the receiver.",
    )
    max_attempts: int = Field(
        default=5,
        ge=1,
        title="Max delivery attempts",
        description="Number of attempts before an alarm report is marked failed.",
    )
    retry_delay_seconds: float = Field(
        default=5.0,
        ge=0,
        title="Retry delay",
        description="Base delay (seconds) between delivery attempts; multiplied by the attempt number.",
    )

    @model_validator(mode="after")
    def require_receiver_details_when_enabled(self) -> "AlarmReportingConfig":
        if self.protocol == AlarmReportingProtocol.none:
            return self
        if not (self.host and self.port and self.account):
            raise ValueError(
                "alarm.reporting.host, port, and account are required when "
                "alarm.reporting.protocol is not 'none'"
            )
        return self


class AlarmWhatsAppConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable WhatsApp notifications",
        description="Send a WhatsApp message on qualifying alarm events via a self-hosted OpenWA instance.",
    )
    api_base_url: str | None = Field(
        default=None,
        title="OpenWA API base URL",
        description="Base URL of your self-hosted OpenWA instance, e.g. https://your-openwa-host/api. No default; must point at your own instance.",
    )
    session_id: str | None = Field(
        default=None,
        title="OpenWA session ID",
        description="The OpenWA session ID to send messages from.",
    )
    api_key: str | None = Field(
        default=None,
        title="OpenWA API key",
        description="API key for your OpenWA instance.",
    )
    to_numbers: list[str] = Field(
        default_factory=list,
        title="Destination numbers",
        description="WhatsApp numbers to notify, e.g. +15551234567.",
    )
    cooldown_seconds: float = Field(
        default=300.0,
        ge=0,
        title="Cooldown",
        description="Minimum seconds between WhatsApp notifications for the same camera/zone, to avoid spamming a phone during a burst of qualifying detections.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        title="Request timeout",
        description="Timeout (seconds) for the OpenWA API request.",
    )

    @model_validator(mode="after")
    def require_details_when_enabled(self) -> "AlarmWhatsAppConfig":
        if not self.enabled:
            return self
        if not (self.api_base_url and self.session_id and self.api_key):
            raise ValueError(
                "alarm.whatsapp.api_base_url, session_id, and api_key are "
                "required when alarm.whatsapp.enabled is true"
            )
        if not self.to_numbers:
            raise ValueError(
                "alarm.whatsapp.to_numbers must not be empty when "
                "alarm.whatsapp.enabled is true"
            )
        return self

    def to_notify_config(self) -> WhatsAppNotifyConfig:
        """Build the plain-dataclass config the notifier evaluates against."""
        assert self.api_base_url and self.session_id and self.api_key
        return WhatsAppNotifyConfig(
            api_base_url=self.api_base_url,
            session_id=self.session_id,
            api_key=self.api_key,
            to_numbers=tuple(self.to_numbers),
            cooldown_seconds=self.cooldown_seconds,
            timeout_seconds=self.timeout_seconds,
        )


class AlarmScheduleEntryConfig(FrigateBaseModel):
    time: str = Field(
        title="Time",
        description="24-hour time (HH:MM) this entry fires at.",
    )
    mode: ArmedMode | None = Field(
        default=None,
        title="Arm mode",
        description="Arm mode to switch to at this time. Leave unset to disarm instead.",
    )
    days: list[int] = Field(
        default_factory=list,
        title="Days",
        description="Days this entry applies on (0=Monday..6=Sunday). Empty applies every day.",
    )

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError as e:
            raise ValueError(
                f"alarm schedule entry time '{v}' must be 24-hour HH:MM"
            ) from e
        return v

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in v):
            raise ValueError(
                "alarm schedule entry days must be 0 (Monday) through 6 (Sunday)"
            )
        return v

    def to_entry(self) -> ScheduleEntry:
        """Build the plain-dataclass entry the scheduler thread evaluates against."""
        return ScheduleEntry(time=self.time, mode=self.mode, days=frozenset(self.days))


class AlarmScheduleConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable schedule",
        description="Automatically arm/disarm the alarm system on a schedule.",
    )
    entries: list[AlarmScheduleEntryConfig] = Field(
        default_factory=list,
        title="Schedule entries",
        description="Time-based arm/disarm actions.",
    )

    def build_entries(self) -> list[ScheduleEntry]:
        """Build the entries the scheduler thread should evaluate."""
        if not self.enabled:
            return []
        return [entry.to_entry() for entry in self.entries]


class AlarmConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable alarm engine",
        description="Enable or disable the alarm engine; can be overridden per-camera.",
    )
    exit_delay_seconds: int = Field(
        default=30,
        ge=0,
        title="Exit delay",
        description="Default seconds to wait after arming before the system is fully armed, giving time to leave.",
    )
    reporting: AlarmReportingConfig = Field(
        default_factory=AlarmReportingConfig,
        title="Reporting",
        description="Central station reporting settings (SIA DC-09 or Contact ID over IP).",
    )
    schedule: AlarmScheduleConfig = Field(
        default_factory=AlarmScheduleConfig,
        title="Schedule",
        description="Automatic arm/disarm schedule.",
    )
    whatsapp: AlarmWhatsAppConfig = Field(
        default_factory=AlarmWhatsAppConfig,
        title="WhatsApp notifications",
        description="Send a WhatsApp message on qualifying alarm events via a self-hosted OpenWA instance.",
    )
    enabled_in_config: bool | None = Field(
        default=None,
        title="Original alarm state",
        description="Indicates whether the alarm engine was enabled in the original static configuration.",
    )
