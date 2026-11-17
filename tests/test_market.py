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


def test_cme_sunday_evening_belongs_to_monday_trade_date():
    calendar = MarketCalendar(
        calendar_id="CME-OVERNIGHT",
        timezone_name="America/Chicago",
        weekdays=(0, 1, 2, 3, 4),
        regular_open=time(18, 0),
        regular_close=time(17, 0),
        open_day_offset=-1,
        close_day_offset=0,
    )
    monday_bounds = calendar.session_bounds(date(2026, 1, 5))
    assert monday_bounds is not None
    assert monday_bounds[0] == datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    assert monday_bounds[1] == datetime(2026, 1, 5, 23, 0, tzinfo=UTC)
    sunday_evening = datetime(2026, 1, 5, 1, 0, tzinfo=UTC)
    assert calendar.is_open(sunday_evening)


def test_24_7_calendar_stays_open_on_weekends():
    calendar = MarketCalendar(
        calendar_id="CRYPTO-24-7",
        timezone_name="UTC",
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        regular_open=time(0, 0),
        regular_close=time(0, 0),
        open_day_offset=0,
        close_day_offset=1,
    )
    assert calendar.is_open(datetime(2026, 1, 3, 12, 0, tzinfo=UTC))


def test_calendar_rejects_unknown_timezone():
    with pytest.raises(ValidationError):
        MarketCalendar(
            calendar_id="BROKEN",
            timezone_name="Mars/Olympus",
            regular_open=time(9),
            regular_close=time(16),
        )


def test_calendar_rejects_close_before_open_without_offset():
    with pytest.raises(ValidationError):
        MarketCalendar(
            calendar_id="BROKEN",
            timezone_name="UTC",
            regular_open=time(18, 0),
            regular_close=time(17, 0),
        )


def test_calendar_rejects_nonexistent_dst_session_boundary():
    calendar = MarketCalendar(
        calendar_id="DST-GAP",
        timezone_name="America/New_York",
        weekdays=(6,),
        regular_open=time(2, 30),
        regular_close=time(4, 0),
    )
    with pytest.raises(ValueError, match="nonexistent local session boundary"):
        calendar.session_bounds(date(2026, 3, 8))


def test_calendar_rejects_ambiguous_dst_session_boundary():
    calendar = MarketCalendar(
        calendar_id="DST-FOLD",
        timezone_name="America/New_York",
        weekdays=(6,),
        regular_open=time(1, 30),
        regular_close=time(3, 0),
    )
    with pytest.raises(ValueError, match="ambiguous local session boundary"):
        calendar.session_bounds(date(2026, 11, 1))
