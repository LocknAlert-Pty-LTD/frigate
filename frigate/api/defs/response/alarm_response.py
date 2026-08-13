from pydantic import BaseModel


class AlarmZoneStatusResponse(BaseModel):
    camera: str
    zone: str
    enabled: bool
    armed: bool


class AlarmStatusResponse(BaseModel):
    state: str
    armed_mode: str | None
    is_alarm_active: bool
    is_alarm_memory: bool
    fault_reason: str | None
    last_transition: str
    reporting_healthy: bool | None
    zones: list[AlarmZoneStatusResponse]


class AlarmEventResponse(BaseModel):
    event_type: str
    camera_id: str
    timestamp: float
    zone_id: str | None
    object_type: str | None
    confidence: float | None
    source: str
    message: str | None
