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

    Session-day offsets define how the session's local open and close dates
    relate to its exchange trading-date label. For Sunday-evening CME sessions
    belonging to Monday's trading date, use open_day_offset=-1 and
    close_day_offset=0. A close not later than the open on the same date needs
    an explicit later close_day_offset.
    """

    calendar_id: str = Field(min_length=1)
    timezone_name: str = Field(min_length=1)
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    regular_open: time
    regular_close: time
    open_day_offset: int = Field(default=0, ge=-3, le=3)
    close_day_offset: int = Field(default=0, ge=-3, le=3)
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
        if len(set(self.holidays)) != len(self.holidays):
            raise ValueError("holidays cannot contain duplicates")
        anchor = date(2000, 1, 3)
        open_date = anchor + timedelta(days=self.open_day_offset)
        close_date = anchor + timedelta(days=self.close_day_offset)
        local_open = datetime.combine(open_date, self.regular_open)
        local_close = datetime.combine(close_date, self.regular_close)
        if local_close <= local_open:
            raise ValueError("close session boundary must be later than open boundary")
        return self

    def session_bounds(self, trading_date: date) -> tuple[datetime, datetime] | None:
        """Return a trading date's open and close in UTC, or None if closed."""
        if trading_date.weekday() not in self.weekdays or trading_date in self.holidays:
            return None

        zone = ZoneInfo(self.timezone_name)
        open_date = trading_date + timedelta(days=self.open_day_offset)
        close_date = trading_date + timedelta(days=self.close_day_offset)
        close_time = self.early_closes.get(trading_date, self.regular_close)
        local_open = _localize_wall_time(open_date, self.regular_open, zone)
        local_close = _localize_wall_time(close_date, close_time, zone)
        if local_close <= local_open:
            raise ValueError(f"early close creates invalid session for {trading_date}")
        return local_open.astimezone(UTC), local_close.astimezone(UTC)

    def is_open(self, instant: datetime) -> bool:
        """Check an aware instant against sessions labelled by trading date."""
        instant_utc = require_utc(instant)
        local_date = instant_utc.astimezone(ZoneInfo(self.timezone_name)).date()
        candidate_dates = {
            local_date - timedelta(days=self.open_day_offset),
            local_date - timedelta(days=self.close_day_offset),
        }
        for trading_date in candidate_dates:
            bounds = self.session_bounds(trading_date)
            if bounds is not None and bounds[0] <= instant_utc < bounds[1]:
                return True
        return False


def _localize_wall_time(day: date, wall_time: time, zone: ZoneInfo) -> datetime:
    """Attach an IANA zone only when the local wall time is unambiguous."""
    naive = datetime.combine(day, wall_time)
    valid: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive:
            valid.append(candidate)
    distinct_offsets = {candidate.utcoffset() for candidate in valid}
    if not valid:
        raise ValueError(f"nonexistent local session boundary: {naive} in {zone.key}")
    if len(distinct_offsets) > 1:
        raise ValueError(f"ambiguous local session boundary: {naive} in {zone.key}")
    return valid[0]
