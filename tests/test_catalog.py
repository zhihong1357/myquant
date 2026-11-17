from datetime import date, time

import pytest

from myquant.catalog import MarketCatalog
from myquant.market import AssetClass, Instrument, InstrumentType, MarketCalendar


def test_catalog_roundtrips_instrument_and_calendar(tmp_path):
    catalog = MarketCatalog(tmp_path)
    instrument = Instrument(
        instrument_id="equity:us:spy",
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.ETF,
        name="SPY",
        quote_currency="USD",
        calendar_id="XNYS",
    )
    calendar = MarketCalendar(
        calendar_id="XNYS",
        timezone_name="America/New_York",
        regular_open=time(9, 30),
        regular_close=time(16, 0),
        holidays=(date(2026, 1, 1),),
    )
    catalog.register_instrument(instrument)
    catalog.register_calendar(calendar)
    assert catalog.get_instrument("equity:us:spy") == instrument
    assert catalog.get_calendar("XNYS") == calendar


def test_catalog_rejects_mutating_an_existing_version(tmp_path):
    catalog = MarketCatalog(tmp_path)
    base = Instrument(
        instrument_id="equity:us:spy",
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.ETF,
        name="SPY",
        quote_currency="USD",
        calendar_id="XNYS",
    )
    catalog.register_instrument(base)
    changed = base.model_copy(update={"name": "Different name"})
    with pytest.raises(FileExistsError):
        catalog.register_instrument(changed)


def test_catalog_requires_new_version_for_changes(tmp_path):
    catalog = MarketCatalog(tmp_path)
    instrument = Instrument(
        instrument_id="equity:us:spy",
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.ETF,
        name="SPY",
        quote_currency="USD",
        calendar_id="XNYS",
    )
    changed = instrument.model_copy(update={"name": "SPDR S&P 500 ETF"})
    catalog.register_instrument(instrument, version=1)
    catalog.register_instrument(changed, version=2)
    assert catalog.get_instrument("equity:us:spy", version=1).name == "SPY"
    assert catalog.get_instrument("equity:us:spy", version=2).name == "SPDR S&P 500 ETF"
