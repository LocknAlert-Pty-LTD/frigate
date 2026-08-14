from typing import Literal

from pydantic import BaseModel


class AlarmArmBody(BaseModel):
    mode: Literal["away", "home", "night"]
    exit_delay_seconds: int | None = None
