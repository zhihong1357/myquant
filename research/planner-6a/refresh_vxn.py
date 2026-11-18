"""Re-fetch the VXN panel (FRED VXNCLS) past the study-003 bound.

Run from the repo root:

    .venv/bin/python research/planner-6a/refresh_vxn.py

The lab's VXN panel ends 2020-05-15 (the study-003 bound), while the
FRED VXNCLS series continues. The 6b evidence probe (2026-11-18)
found the panel 2,377 days stale. This script pulls the full
VXNCLS history from the free fredgraph CSV endpoint (no key, no
custom User-Agent — see the adapter notes), stores the raw payload
in the gitignored cache under data/cache/vxn-panel-refresh/raw/
(content-addressed RawStore), checks the overlap with the old
panel against the committed study-003 manifest, checks the seam
where the new data starts, writes the refresh manifest
(research/planner-6a/vxn_refresh.json), and updates the VXN node
in research/planner-6a/data_availability.json.

What this script does NOT do: it does not touch study 003 (its
panel, results, reports and manifest are fixed records), it does
not re-run any study, register any hypothesis or run any trial,
and it does not analyse the refreshed data. The refreshed panel
exists only so the planner can rank the 12 VXN pairs that were
unrankable for lack of an overlapping window.

Overlap check, stated honestly: the study-003 raw payload lives
only in the gitignored cache and was not retained locally, so a
value-by-value comparison against the original pull is impossible
from the retained records. The overlap check is therefore
aggregate-level: the new pull's 2003-01-02 to 2020-05-15 window
(the study-003 fetch window) must match the committed study-003
manifest exactly (4,372 rows, 161 missing values, 2003-01-02 to
2020-05-15). A value-level revision that preserved those aggregates
cannot be excluded from the retained records, and the manifest
says so. If the aggregates do not match, the script records the
mismatch and refuses to update the availability config.
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from myquant.adapters.fred import (  # noqa: E402
    DAILY_CLOSE_UTC,
    fetch_series,
)
from myquant.raw import RawStore  # noqa: E402

SERIES_ID = "VXNCLS"
INSTRUMENT_ID = "index:vxn"
OLD_WINDOW_START = date(2003, 1, 2)
OLD_PANEL_LAST = date(2020, 5, 15)
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "vxn-panel-refresh"
STUDY_003_MANIFEST = REPO_ROOT / "research/move-vix-003/manifest.json"
AVAILABILITY_PATH = ROOT / "data_availability.json"
REFRESH_MANIFEST_PATH = ROOT / "vxn_refresh.json"

# Committed study-003 record for the VXN fetch (manifest.json,
# fetches[] entry for index:vxn). Read from the manifest at run
# time; these literals are only the fail-fast expectation.
EXPECTED_OVERLAP = {
    "rows": 4372,
    "missing_values": 161,
    "first_date": "2003-01-02",
    "last_date": "2020-05-15",
}


def _old_panel_record() -> dict:
    """The study-003 manifest's VXN fetch entry (read-only)."""
    manifest = json.loads(STUDY_003_MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["fetches"]:
        if entry["instrument_id"] == INSTRUMENT_ID:
            return entry
    raise AssertionError(f"{INSTRUMENT_ID} not in the study-003 manifest")


def _missing_forms(payload: bytes) -> dict[str, int]:
    """Count the missing-value encodings in the raw CSV.

    Study 003 verified that FRED fredgraph CSVs encode missing
    values as empty fields, not ".". Count both forms so a change
    in the encoding would show up here.
    """
    text = payload.decode("utf-8")
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    empty = sum(1 for row in rows[1:] if row[1] == "")
    dotted = sum(1 for row in rows[1:] if row[1] == ".")
    return {"empty_field": empty, "dot": dotted}


def _seam_check(
    observations: tuple[tuple[date, float], ...],
) -> dict:
    """Describe the seam where the new data starts (descriptive only).

    Compares the log change across the seam (last old-panel value
    to first post-seam value) with the distribution of daily log
    changes in the new segment. No conclusion is drawn; the numbers
    are reported so a gross discontinuity would be visible.
    """
    overlap = [(d, v) for d, v in observations if d <= OLD_PANEL_LAST]
    new = [(d, v) for d, v in observations if d > OLD_PANEL_LAST]
    if not overlap or not new:
        raise AssertionError("overlap or new segment is empty")
    last_old_date, last_old_value = overlap[-1]
    first_new_date, first_new_value = new[0]
    seam_log_change = math.log(first_new_value / last_old_value)
    new_changes = [
        abs(math.log(new[i + 1][1] / new[i][1])) for i in range(len(new) - 1)
    ]
    new_changes.sort()
    median = new_changes[len(new_changes) // 2]
    p99 = new_changes[int(0.99 * (len(new_changes) - 1))]
    return {
        "last_overlap_value": {
            "date": last_old_date.isoformat(),
            "value": last_old_value,
        },
        "first_new_value": {
            "date": first_new_date.isoformat(),
            "value": first_new_value,
        },
        "seam_log_change": seam_log_change,
        "new_segment_abs_log_change_median": median,
        "new_segment_abs_log_change_p99": p99,
        "seam_within_p99": abs(seam_log_change) <= p99,
    }


def main() -> None:
    fetched_at = datetime.now(UTC)
    old = _old_panel_record()
    for key, expected in EXPECTED_OVERLAP.items():
        if old[key] != expected:
            raise AssertionError(
                f"study-003 manifest changed: {key} is {old[key]!r}, "
                f"expected {expected!r}; refusing to guess the baseline"
            )

    series = fetch_series(SERIES_ID)
    if any(value <= 0 for _, value in series.observations):
        raise ValueError(f"{SERIES_ID}: non-positive close found")

    last_event_time = datetime.combine(
        series.observations[-1][0],
        DAILY_CLOSE_UTC,
        tzinfo=UTC,
    )
    raw_store = RawStore(CACHE_ROOT / "raw")
    record = raw_store.put(
        series.payload,
        source_id="fred",
        available_at=fetched_at,
        content_type="text/csv",
        source_version=1,
        event_time=last_event_time,
        ingested_at=fetched_at,
    )

    # Missing dates, by segment (the adapter drops them from
    # observations, so re-derive them from the raw payload).
    text = series.payload.decode("utf-8")
    rows = [row for row in csv.reader(io.StringIO(text)) if row][1:]
    missing_dates = [
        date.fromisoformat(row[0]) for row in rows if row[1] in ("", ".")
    ]
    overlap_missing = [
        d for d in missing_dates if OLD_WINDOW_START <= d <= OLD_PANEL_LAST
    ]
    new_missing = [d for d in missing_dates if d > OLD_PANEL_LAST]
    pre_window_missing = [d for d in missing_dates if d < OLD_WINDOW_START]

    overlap_obs = [
        o
        for o in series.observations
        if OLD_WINDOW_START <= o[0] <= OLD_PANEL_LAST
    ]
    pre_window_obs = [
        o for o in series.observations if o[0] < OLD_WINDOW_START
    ]
    new_obs = [o for o in series.observations if o[0] > OLD_PANEL_LAST]
    overlap = {
        "rows": len(overlap_obs),
        "missing_values": len(overlap_missing),
        "first_date": overlap_obs[0][0].isoformat(),
        "last_date": overlap_obs[-1][0].isoformat(),
    }
    overlap_match = all(
        overlap[key] == EXPECTED_OVERLAP[key] for key in EXPECTED_OVERLAP
    )

    manifest: dict = {
        "series": SERIES_ID,
        "instrument_id": INSTRUMENT_ID,
        "fetched_at": fetched_at.isoformat(),
        "endpoint": series.url,
        "cache_root": "data/cache/vxn-panel-refresh",
        "payload_sha256": record.payload_sha256,
        "record_id": record.record_id,
        "full_series": {
            "rows": len(series.observations),
            "missing_values": series.missing_count,
            "missing_forms": _missing_forms(series.payload),
            "first_date": series.observations[0][0].isoformat(),
            "last_date": series.observations[-1][0].isoformat(),
        },
        "old_panel_baseline": {
            "source": "research/move-vix-003/manifest.json (fetches entry "
            "for index:vxn; study 003 not modified)",
            "rows": EXPECTED_OVERLAP["rows"],
            "missing_values": EXPECTED_OVERLAP["missing_values"],
            "first_date": EXPECTED_OVERLAP["first_date"],
            "last_date": EXPECTED_OVERLAP["last_date"],
            "payload_sha256": old["payload_sha256"],
        },
        "overlap_check": {
            "segment": (
                f"{OLD_WINDOW_START.isoformat()} to "
                f"{OLD_PANEL_LAST.isoformat()} (the study-003 window)"
            ),
            "rows": overlap["rows"],
            "missing_values": overlap["missing_values"],
            "first_date": overlap["first_date"],
            "last_date": overlap["last_date"],
            "matches_study_003_manifest": overlap_match,
            "method": "Aggregate-level only: the study-003 raw payload "
            "lives in the gitignored cache and was not retained "
            "locally, so no value-by-value comparison against the "
            "original pull is possible from the retained records. "
            "A value-level revision that preserved the row and "
            "missing counts cannot be excluded.",
        },
        "pre_window_segment": {
            "segment": (
                "before the study-003 window: the full series starts "
                f"{series.observations[0][0].isoformat()}, study 003 "
                f"fetched from {OLD_WINDOW_START.isoformat()}"
            ),
            "first_date": pre_window_obs[0][0].isoformat(),
            "last_date": pre_window_obs[-1][0].isoformat(),
            "rows": len(pre_window_obs),
            "missing_values": len(pre_window_missing),
        },
        "new_segment": {
            "first_date": new_obs[0][0].isoformat(),
            "last_date": new_obs[-1][0].isoformat(),
            "rows": len(new_obs),
            "missing_values": len(new_missing),
            "missing_dates": [d.isoformat() for d in new_missing],
        },
        "seam_check": _seam_check(series.observations),
    }

    REFRESH_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"refresh manifest written: {REFRESH_MANIFEST_PATH}")
    print(
        f"full series: {len(series.observations)} rows, "
        f"{series.missing_count} missing, "
        f"{series.observations[0][0]} to {series.observations[-1][0]}"
    )
    print(
        f"overlap ({OLD_WINDOW_START} to {OLD_PANEL_LAST}): "
        f"{overlap['rows']} rows, "
        f"{overlap['missing_values']} missing; matches study-003 "
        f"manifest: {overlap_match}"
    )
    if not overlap_match:
        print(
            "OVERLAP MISMATCH: refusing to update data_availability.json. "
            "See the refresh manifest for the differing aggregates."
        )
        raise SystemExit(1)

    # Update the VXN node only; every other node is untouched.
    availability = json.loads(AVAILABILITY_PATH.read_text(encoding="utf-8"))
    panels = availability["panels"]
    vxn = next(p for p in panels if p["instrument_id"] == INSTRUMENT_ID)
    vxn["rows"] = len(series.observations)
    vxn["first"] = series.observations[0][0].isoformat()
    vxn["last"] = series.observations[-1][0].isoformat()
    vxn["notes"] = (
        "Re-fetched past 2020-05-15 (see research/planner-6a/"
        "vxn_refresh.json): the full FRED VXNCLS history, verified "
        f"{fetched_at.date().isoformat()}. The study-003 panel "
        "(2003-01-02 to 2020-05-15) is unchanged; the overlap "
        "segment of the new pull matches its manifest aggregates "
        "exactly (4,372 rows, 161 missing)."
    )
    vxn["verified_by"] = (
        "research/planner-6a/vxn_refresh.json (full VXNCLS pull: "
        f"{len(series.observations)} rows, {series.missing_count} "
        "missing values)"
    )
    AVAILABILITY_PATH.write_text(
        json.dumps(availability, indent=4, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"availability updated: {AVAILABILITY_PATH} (VXN node only)")


if __name__ == "__main__":
    main()
