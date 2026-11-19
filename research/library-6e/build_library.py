"""Build the lab catalog and status report (Stage 6e).

Deterministic and offline: reads only committed local files, never
the network and never market data. Writes three artifacts into
``research/library-6e/`` (or ``--out-dir``):

- ``catalog.json`` — the unified catalog (studies, hypotheses,
  trials, edges, decision records, candidates, sources, panels,
  review and audit summaries, broken links, missing optional files)
- ``lab_report.md`` — the human-readable lab status report
- ``lab_report.json`` — the same report content as structured data

The generation timestamp is an input parameter (``--generated-at``,
ISO 8601); two runs with the same timestamp produce byte-identical
outputs. The drift test in ``tests/test_librarian.py`` rebuilds with
the committed timestamp and compares bytes.

Usage (from the repo root):

    .venv/bin/python research/library-6e/build_library.py
    .venv/bin/python research/library-6e/build_library.py \\
        --generated-at 2026-11-19T00:00:00+00:00 --out-dir /tmp/lib
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from myquant.librarian import (  # noqa: E402
    build_catalog,
    render_catalog_json,
    render_lab_report_json,
    render_lab_report_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "research" / "library-6e"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO timestamp for the catalog (default: now, UTC)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="repo root to scan (default: the repo this script lives in)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="directory to write the three artifacts into",
    )
    args = parser.parse_args()
    generated_at = (
        datetime.fromisoformat(args.generated_at)
        if args.generated_at is not None
        else datetime.now(UTC)
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog = build_catalog(Path(args.repo_root), generated_at)
    (out_dir / "catalog.json").write_bytes(render_catalog_json(catalog))
    (out_dir / "lab_report.md").write_text(
        render_lab_report_markdown(catalog), encoding="utf-8"
    )
    (out_dir / "lab_report.json").write_bytes(
        render_lab_report_json(catalog)
    )

    counts = catalog.counts
    print(
        f"catalog: {counts['studies']} studies, "
        f"{counts['trials_total']} trials "
        f"({counts['trials_completed']} completed, "
        f"{counts['trials_failed']} failed, "
        f"{counts['trials_reserved']} reserved), "
        f"{counts['edges_total']} edges, "
        f"{counts['decision_records']} decision records, "
        f"{counts['candidates_total']} candidates"
    )
    print(
        f"integrity: {counts['broken_links']} broken link(s), "
        f"{counts['missing_optional']} missing optional file(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
