"""Frozen Bazi calculation conventions, independent of HTTP and interpretation."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictBool

class BaziOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    true_solar_time: StrictBool = True
    day_boundary: Literal['23:00', '00:00'] = '23:00'
