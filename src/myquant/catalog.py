"""Versioned instrument and calendar master catalog."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from myquant.market import Instrument, MarketCalendar
from myquant.sources import _write_new_file


class MarketCatalog:
    """Persist immutable versions of instrument definitions and calendars."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def register_instrument(self, instrument: Instrument, *, version: int = 1) -> Path:
        return self._register("instruments", instrument.instrument_id, instrument, version)

    def get_instrument(self, instrument_id: str, *, version: int = 1) -> Instrument:
        return Instrument.model_validate_json(
            self._path("instruments", instrument_id, version).read_text(encoding="utf-8")
        )

    def register_calendar(self, calendar: MarketCalendar, *, version: int = 1) -> Path:
        return self._register("calendars", calendar.calendar_id, calendar, version)

    def get_calendar(self, calendar_id: str, *, version: int = 1) -> MarketCalendar:
        return MarketCalendar.model_validate_json(
            self._path("calendars", calendar_id, version).read_text(encoding="utf-8")
        )

    def _register(self, kind: str, key: str, model: Instrument | MarketCalendar, version: int) -> Path:
        path = self._path(kind, key, version)
        payload = model.model_dump_json(indent=2).encode("utf-8") + b"\n"
        _write_new_file(path, payload)
        return path

    def _path(self, kind: str, key: str, version: int) -> Path:
        if version < 1:
            raise ValueError("version must be >= 1")
        if not key or key in {".", ".."}:
            raise ValueError("catalog key must be non-empty")
        safe_key = quote(key, safe="")
        return self.root / kind / safe_key / f"v{version}.json"
