"""Canonical instruments and exchange-session calendars."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from myquant.contracts import StrictContract, require_utc


class AssetClass(StrEnum):
    RATES = "rates"
    CREDIT = "credit"
    EQUITY = "equity"
    OPTIONS = "options"
    FUTURES = "futures"
    FX = "fx"
    COMMODITIES = "commodities"
    CRYPTO = "crypto"
    INDEX = "index"
    VOLATILITY = "volatility"
    MACRO = "macro"


class InstrumentType(StrEnum):
    SPOT = "spot"
    FUTURE = "future"
    PERPETUAL = "perpetual"
    OPTION = "option"
    ETF = "etf"
    STOCK = "stock"
    BOND = "bond"
    CDS = "cds"
    RATE = "rate"
    INDEX = "index"
    MACRO_SERIES = "macro_series"


class Instrument(StrictContract):
    """Provider-neutral identity; provider symbols belong in source mappings."""

    instrument_id: str = Field(min_length=3, pattern=r"^[a-z0-9][a-z0-9:_./-]+$")
    asset_class: AssetClass
    instrument_type: InstrumentType
    name: str = Field(min_length=1)
    quote_currency: str | None = Field(default=None, min_length=3, max_length=12)
    calendar_id: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MarketCalendar(StrictContract):
    """Recurring local sessions plus holidays and date-specific early closes.

    A close time less than or equal to the open time denotes an overnight
    session. For a continuous 24/7 calendar use all seven weekdays and 00:00
    for both open and close.
    """

    calendar_id: str = Field(min_length=1)
    timezone_name: str = Field(min_length=1)
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    regular_open: time
    regular_close: time
    holidays: tuple[date, ...] = ()
    early_closes: dict[date, time] = Field(default_factory=dict)

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def validate_calendar(self) -> MarketCalendar:
        if not self.weekdays or any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("weekdays must contain values from 0 (Mon) to 6 (Sun)")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays cannot contain duplicates")
        if set(self.early_closes).difference(self.holidays) and False:
            raise ValueError("unreachable")
        return self

    def session_bounds(self, trading_date: date) -> tuple[datetime, datetime] | None:
        """Return a trading date's open and close in UTC, or None if closed."""
        if trading_date.weekday() not in self.weekdays or trading_date in self.holidays:
            return None

        zone = ZoneInfo(self.timezone_name)
        close_time = self.early_closes.get(trading_date, self.regular_close)
        local_open = datetime.combine(trading_date, self.regular_open, tzinfo=zone)
        close_date = trading_date
        if close_time <= self.regular_open:
            close_date += timedelta(days=1)
        local_close = datetime.combine(close_date, close_time, tzinfo=zone)
        return local_open.astimezone(UTC), local_close.astimezone(UTC)

    def is_open(self, instant: datetime) -> bool:
        """Check whether an aware instant falls inside a regular session."""
        instant_utc = require_utc(instant)
        local_date = instant_utc.astimezone(ZoneInfo(self.timezone_name)).date()
        for candidate in (local_date - timedelta(days=1), local_date):
            bounds = self.session_bounds(candidate)
            if bounds is not None and bounds[0] <= instant_utc < bounds[1]:
                return True
        return False
