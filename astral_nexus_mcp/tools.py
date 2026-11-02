"""Read-only deterministic calculations, independent of HTTP, accounts and AI."""
from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from astral_nexus_mcp.engines import astrology, bazi, bazi_luck
from astral_nexus_mcp.engines.astrology_options import AstrologyOptions, settings_for_options
from astral_nexus_mcp.engines.bazi_options import BaziOptions
from astral_nexus_mcp.engines.birth_time import utc_birth


class Location(BaseModel):
    model_config = ConfigDict(extra='forbid')
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class BirthInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    birth_date: date
    local_time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    timezone: str = Field(min_length=1, max_length=100, description='IANA timezone, e.g. Asia/Shanghai')
    location: Location
    sex: Literal['M', 'F'] | None = Field(default=None, description='Required only for Bazi luck cycles')

    def profile(self):
        value = self.model_dump()
        value['time_precision'] = 'exact'
        utc_birth(value)  # Reject DST gaps/overlaps rather than guess.
        return value


def calculate_astrology(birth: BirthInput, options: AstrologyOptions | None = None) -> dict[str, object]:
    """Calculate a tropical natal chart. Returns facts, no AI interpretation or saved report."""
    selected = options or AstrologyOptions()
    settings = selected.model_dump()
    result, _ = astrology.calculate(birth.profile(), settings)
    return {'service_id': 'astrology', 'engine_version': astrology.ENGINE_VERSION,
            'settings': {**settings_for_options(settings), 'calculation_options': settings},
            'result': result, 'limitations': ['Natal calculation only; no AI report or annual forecast.']}


def calculate_bazi(birth: BirthInput, options: BaziOptions | None = None,
                   through_year: Annotated[int | None, Field(ge=1800, le=2399)] = None) -> dict[str, object]:
    """Calculate four pillars, hidden stems and ten gods. Optional luck cycles require sex and through_year.

    Does not determine patterns, favorable elements or personal fortune judgments.
    """
    selected = options or BaziOptions()
    profile = birth.profile()
    basis = 'apparent_solar' if selected.true_solar_time else 'civil'
    result, _ = bazi.calculate(profile, basis, selected.day_boundary)
    if through_year is not None:
        luck, _ = bazi_luck.calculate(profile, result, through_year)
        result['luck'] = {'engine_version': bazi_luck.ENGINE_VERSION,
                          'settings': bazi_luck.SETTINGS, 'result': luck}
    return {'service_id': 'bazi-chart', 'engine_version': bazi.ENGINE_VERSION,
            'settings': bazi.settings_for(basis, selected.day_boundary), 'result': result,
            'limitations': ['No pattern selection, favorable elements or AI interpretation.']}
