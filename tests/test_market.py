from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from myquant.market import AssetClass, Instrument, InstrumentType, MarketCalendar


def test_instrument_uses_provider_neutral_identity():
    instrument = Instrument(
        instrument_id="equity:us:spy",
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.ETF,
        name="SPDR S&P 500 ETF Trust",
        quote_currency="USD",
        calendar_id="XNYS",
    )
    assert instrument.instrument_id == "equity:us:spy"


def test_calendar_converts_new_york_session_to_utc():
    calendar = MarketCalendar(
        calendar_id="XNYS",
        timezone_name="America/New_York",
        regular_open=time(9, 30),
        regular_close=time(16, 0),
    )
    bounds = calendar.session_bounds(date(2026, 1, 5))
    assert bounds is not None
    assert bounds[0] == datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    assert bounds[1] == datetime(2026, 1, 5, 21, 0, tzinfo=UTC)


def test_calendar_holiday_and_early_close():
    calendar = MarketCalendar(
        calendar_id="XNYS",
        timezone_name="America/New_York",
        regular_open=time(9, 30),
        regular_close=time(16, 0),
        holidays=(date(2026, 1, 1),),
        early_closes={date(2026, 11, 27): time(13, 0)},
    )
    assert calendar.session_bounds(date(2026, 1, 1)) is None
    bounds = calendar.session_bounds(date(2026, 11, 27))
    assert bounds is not None
    assert bounds[1] == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)


def test_overnight_session_is_open_after_midnight():
    calendar = MarketCalendar(
        calendar_id="CME-OVERNIGHT",
        timezone_name="America/Chicago",
        weekdays=(0, 1, 2, 3, 4),
        regular_open=time(18, 0),
        regular_close=time(17, 0),
    )
    instant = datetime(2026, 1, 6, 7, 0, tzinfo=UTC)
    assert calendar.is_open(instant)


def test_calendar_rejects_unknown_timezone():
    with pytest.raises(ValidationError):
        MarketCalendar(
            calendar_id="BROKEN",
            timezone_name="Mars/Olympus",
            regular_open=time(9),
            regular_close=time(16),
        )
