"""Source registry contracts for the evidence analyst (Stage 6b).

The registry is the lab's single record of where its data comes
from: one entry per public source, hand-written from the studies'
verified findings, each quirk cited to the study and date that
verified it. It is data, not code: the probe script reads it, the
checks validate against it, and nothing here touches the network.

Two honesty rules shape the schema:

- Every quirk carries ``verified_by`` (study) and ``verified_date``,
  plus a ``recheck`` method when the fact can be re-verified live.
  Quirks the probe cannot re-check (an expensive bisection, a
  time-of-day observation) are marked ``recorded_only`` and stay in
  the report as recorded facts, never as fresh verifications.
- A source is either ``automatic`` (the probe may fetch it) or
  ``manual-only`` (no automated probe exists — BLS returns HTTP 403
  to programmatic requests, so the registry records the manual
  check instead of pretending a curl would work).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator

from myquant.contracts import StrictContract


class ProbeKind(StrEnum):
    """Whether the probe script may fetch this source automatically."""

    AUTOMATIC = "automatic"
    MANUAL_ONLY = "manual-only"


class CheckKind(StrEnum):
    """Which pure check function validates a probe payload."""

    OKX_CANDLES = "okx_candles"
    DERIBIT_INSTRUMENTS = "deribit_instruments"
    DERIBIT_DVOL = "deribit_dvol"
    FRED_CSV = "fred_csv"
    YAHOO_CHART = "yahoo_chart"
    FED_PAGE = "fed_page"
    FISCAL_API = "fiscal_api"
    HYPERLIQUID_MIDS = "hyperliquid_mids"


class LagKind(StrEnum):
    """How a panel's expected latest point is derived from probe time.

    FRED_BUSINESS_DAY: the previous trading day (weekday calendar,
    the study-007 convention — market holidays are not modelled).
    OKX_DAILY_BAR: the latest 1D bar that has completed (bars open
    16:00 UTC and complete 24 hours later). DVOL_DAILY: yesterday's
    point (DVOL points are timestamped 00:00 UTC and complete the
    next day). YAHOO_CLOSE: the latest US equity close (16:00 ET,
    recorded as 21:00 UTC by the lab's fixed convention).
    CPI_MONTHLY: the latest reference month whose BLS release date
    has passed. DISCONTINUED: the series has ended; the panel end
    is the series end and is the expected state, not staleness.
    """

    FRED_BUSINESS_DAY = "fred_business_day"
    OKX_DAILY_BAR = "okx_daily_bar"
    DVOL_DAILY = "dvol_daily"
    YAHOO_CLOSE = "yahoo_close"
    CPI_MONTHLY = "cpi_monthly"
    DISCONTINUED = "discontinued"


class SourceEndpoint(StrictContract):
    """One endpoint of a source that the lab uses."""

    path: Annotated[str, Field(min_length=1)]
    used_for: Annotated[str, Field(min_length=1)]
    expected_structure: Annotated[str, Field(min_length=1)]


class SourceQuirk(StrictContract):
    """One verified characteristic of a source, with its citation.

    ``recorded_only`` means the live probe does not re-verify this
    fact (too expensive, or only observable at a specific time of
    day); it stays in the report as a recorded fact with its
    citation and its ``recheck`` method for a future manual check.
    """

    statement: Annotated[str, Field(min_length=1)]
    verified_by: Annotated[str, Field(min_length=1)]
    verified_date: date
    recheck: Annotated[str, Field(min_length=1)] | None = None
    recorded_only: bool = False


class SourceProbe(StrictContract):
    """One small probe request the script may make for a source.

    ``url_template`` may use the placeholders ``{window_start}``
    (probe date minus 10 days, ISO date), ``{window_start_60}``
    (probe date minus 60 days, ISO date, for monthly series and
    lagging APIs), ``{probe_date}`` (ISO date), ``{period1}`` and
    ``{period2}`` (Unix seconds bounding the window), and
    ``{period1_ms}`` / ``{period2_ms}`` (the same bounds in
    milliseconds); a template with no placeholders is fetched
    as-is. ``user_agent`` of None means the request sends no
    User-Agent header (FRED's edge hangs on browser-like UAs).
    One probe is one request: no retries, no paging.
    """

    key: Annotated[str, Field(min_length=1)]
    method: Annotated[str, Field(pattern=r"^(GET|POST)$")] = "GET"
    url_template: Annotated[str, Field(min_length=1)]
    user_agent: Annotated[str, Field(min_length=1)] | None = None
    timeout_seconds: Annotated[float, Field(gt=0.0)] = 30.0
    check_kind: CheckKind
    check_params: dict[str, str] = {}
    body_template: Annotated[str, Field(min_length=1)] | None = None


class SourceRecord(StrictContract):
    """One data source the lab uses, with its verified behaviour."""

    source_id: Annotated[str, Field(min_length=1)]
    provider: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]
    base_url: Annotated[str, Field(min_length=1)]
    auth: Annotated[str, Field(min_length=1)]
    used_by: tuple[Annotated[str, Field(min_length=1)], ...]
    endpoints: tuple[SourceEndpoint, ...]
    quirks: tuple[SourceQuirk, ...]
    retention: Annotated[str, Field(min_length=1)]
    probe_kind: ProbeKind
    probes: tuple[SourceProbe, ...] = ()
    manual_check: Annotated[str, Field(min_length=1)] | None = None
    last_verified: date

    @model_validator(mode="after")
    def validate_probe_kind(self) -> SourceRecord:
        if self.probe_kind is ProbeKind.MANUAL_ONLY:
            if self.probes:
                raise ValueError(
                    f"manual-only source {self.source_id!r} must not "
                    "declare probes"
                )
            if self.manual_check is None:
                raise ValueError(
                    f"manual-only source {self.source_id!r} needs a "
                    "manual_check method"
                )
        else:
            if not self.probes:
                raise ValueError(
                    f"automatic source {self.source_id!r} needs at "
                    "least one probe"
                )
            if self.manual_check is not None:
                raise ValueError(
                    f"automatic source {self.source_id!r} must not "
                    "declare a manual_check"
                )
        keys = [probe.key for probe in self.probes]
        if len(set(keys)) != len(keys):
            raise ValueError(
                f"source {self.source_id!r} has duplicate probe keys"
            )
        return self


class EvidenceRegistry(StrictContract):
    """The lab's data-source registry: one record per source."""

    schema_version: Annotated[int, Field(ge=1)] = 1
    sources: tuple[SourceRecord, ...]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> EvidenceRegistry:
        ids = [source.source_id for source in self.sources]
        if len(set(ids)) != len(ids):
            raise ValueError("source ids must be unique")
        return self

    def source(self, source_id: str) -> SourceRecord:
        """The record for a source id, or ValueError when unknown.

        Unknown ids are refused, never guessed: a check request for
        a source the registry does not know is a caller error.
        """
        for record in self.sources:
            if record.source_id == source_id:
                return record
        raise ValueError(f"unknown source id: {source_id!r}")

    def probe(self, source_id: str, probe_key: str) -> SourceProbe:
        """One probe of one source, or ValueError when either is unknown."""
        record = self.source(source_id)
        for probe in record.probes:
            if probe.key == probe_key:
                return probe
        raise ValueError(
            f"unknown probe {probe_key!r} for source {source_id!r}"
        )


class PanelFreshnessRule(StrictContract):
    """How one registered panel's freshness is judged.

    ``latest_from`` names the probe key whose check evidence carries
    the observed latest point for this panel (e.g. ``"fred:VIXCLS"``;
    several panels may share one probe key when they share a grid,
    such as the three OKX perpetuals). ``series_end`` is set only
    for discontinued series, where the panel end is the expected
    state rather than staleness.
    """

    instrument_id: Annotated[str, Field(min_length=1)]
    source_id: Annotated[str, Field(min_length=1)]
    lag_kind: LagKind
    latest_from: Annotated[str, Field(min_length=1)]
    series_end: date | None = None
    notes: str = ""

    @model_validator(mode="after")
    def validate_discontinued(self) -> PanelFreshnessRule:
        if self.lag_kind is LagKind.DISCONTINUED and self.series_end is None:
            raise ValueError(
                f"discontinued panel {self.instrument_id!r} needs a series_end"
            )
        if self.lag_kind is not LagKind.DISCONTINUED and self.series_end is not None:
            raise ValueError(
                f"non-discontinued panel {self.instrument_id!r} must not "
                "set series_end"
            )
        return self


class PanelFreshnessConfig(StrictContract):
    """Freshness rules for the planner's registered panels."""

    schema_version: Annotated[int, Field(ge=1)] = 1
    panels: tuple[PanelFreshnessRule, ...]

    @model_validator(mode="after")
    def validate_unique_panels(self) -> PanelFreshnessConfig:
        ids = [panel.instrument_id for panel in self.panels]
        if len(set(ids)) != len(ids):
            raise ValueError("panel instrument ids must be unique")
        return self

    def rule(self, instrument_id: str) -> PanelFreshnessRule:
        """The freshness rule for a panel, or ValueError when unknown."""
        for panel in self.panels:
            if panel.instrument_id == instrument_id:
                return panel
        raise ValueError(f"unknown panel instrument id: {instrument_id!r}")


def load_registry(path: str | Path) -> EvidenceRegistry:
    """Load and validate the source registry."""
    return EvidenceRegistry.model_validate_json(Path(path).read_text())


def load_panel_freshness(path: str | Path) -> PanelFreshnessConfig:
    """Load and validate the panel freshness rules."""
    return PanelFreshnessConfig.model_validate_json(Path(path).read_text())
