"""Global alarm engine configuration."""

from enum import Enum

from pydantic import Field, model_validator

from .base import FrigateBaseModel

__all__ = ["AlarmConfig", "AlarmReportingConfig", "AlarmReportingProtocol"]


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
    enabled_in_config: bool | None = Field(
        default=None,
        title="Original alarm state",
        description="Indicates whether the alarm engine was enabled in the original static configuration.",
    )
