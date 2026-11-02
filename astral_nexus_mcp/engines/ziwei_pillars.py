"""Resolve four known pillars to explicit, user-selected civil occurrences."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from lunar_python import Solar
from astral_nexus_mcp.engines.birth_time import CalculationError

class PillarInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day_boundary: Literal['23:00','00:00'] = '23:00'
    year: str
    month: str
    day: str
    hour: str
    base_year: int = Field(default=1900, ge=1800, le=2399)
    end_year: int = Field(default_factory=lambda: datetime.now(timezone.utc).year, ge=1800, le=2399)

    @field_validator('year','month','day','hour')
    @classmethod
    def ganzhi(cls, value):
        valid = ['甲乙丙丁戊己庚辛壬癸'[i%10]+'子丑寅卯辰巳午未申酉戌亥'[i%12] for i in range(60)]
        if value not in valid: raise ValueError('请输入有效的六十甲子干支')
        return value

def candidates(value):
    data = PillarInput.model_validate(value)
    if data.end_year < data.base_year or data.end_year-data.base_year>200: raise CalculationError('INVALID_PILLARS','检索年份范围须为0至200年')
    # lunar_python searches up to the present year. Do not imply future occurrences are covered.
    if data.end_year > datetime.now(timezone.utc).year: raise CalculationError('INVALID_PILLARS','检索结束年不能晚于当前年')
    values = Solar.fromBaZi(data.year,data.month,data.day,data.hour,sect=1 if data.day_boundary=='23:00' else 2,base_year=data.base_year)
    return [{'birth_date':v.toYmd(),'local_time':v.toYmdHms()[11:16]} for v in values if data.base_year<=v.getYear()<=data.end_year]
