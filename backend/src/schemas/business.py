from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CleanInput(BaseModel, str_strip_whitespace=True, extra='forbid'):
    pass


class Login(CleanInput):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class SleeveInput(CleanInput):
    code: str = Field(pattern=r'^[A-Z0-9-]{2,32}$')
    title: str = Field(min_length=2, max_length=100)
    pack_size: int = Field(ge=1, le=10000)
    lead_weeks: int = Field(ge=1, le=8)


class UsageInput(CleanInput):
    sleeve_code: str = Field(max_length=32)
    week: date
    state: Literal['observed', 'missing']
    units: int | None = Field(default=None, ge=0, le=10000)

    @model_validator(mode='after')
    def validate_week(self):
        if self.week.weekday() != 0:
            raise ValueError('周日期必须填星期一')
        if (self.state == 'observed') != (self.units is not None):
            raise ValueError('已核周必须填领用量，可为零；缺传周必须留空')
        return self


class AnalysisInput(CleanInput):
    title: str = Field(min_length=2, max_length=100)
    sleeve_code: str = Field(max_length=32)
    alpha: float = Field(ge=0.05, le=0.5, default=.2)
    baseline_weeks: int = Field(ge=4, le=16, default=8)


class Publication(CleanInput):
    note: str = Field(min_length=3, max_length=400)
