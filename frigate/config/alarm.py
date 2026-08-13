"""Global alarm engine configuration."""

from pydantic import Field

from .base import FrigateBaseModel

__all__ = ["AlarmConfig"]


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
    enabled_in_config: bool | None = Field(
        default=None,
        title="Original alarm state",
        description="Indicates whether the alarm engine was enabled in the original static configuration.",
    )
