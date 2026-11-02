"""Validated, frozen natal options. No HTTP or interpretation dependencies."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool

HOUSES = {'P': 'Placidus', 'K': 'Koch', 'W': 'Whole Sign', 'E': 'Equal',
          'O': 'Porphyry', 'R': 'Regiomontanus', 'C': 'Campanus'}

class AstrologyOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    house_system: Literal['P','K','W','E','O','R','C'] = 'P'
    node_mode: Literal['mean','true'] = 'mean'
    orb_scale: Literal[0.5,1,1.5] = 1
    include_asteroids: StrictBool = False

class Relocation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=200)
    latitude: float = Field(ge=-90,le=90,allow_inf_nan=False)
    longitude: float = Field(ge=-180,le=180,allow_inf_nan=False)

REFERENCE_ORBS={'conjunction':8,'opposition':8,'trine':8,'square':8,'sextile':6}

def settings_for_options(value):
    options=AstrologyOptions.model_validate(value)
    return {'zodiac':'tropical','house_system':HOUSES[options.house_system],
            'ephemeris':'Swiss Ephemeris',
            'aspect_orbs_degrees':{k:v*options.orb_scale for k,v in REFERENCE_ORBS.items()}}
