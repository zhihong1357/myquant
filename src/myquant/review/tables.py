"""Markdown results-table parsing and report-ledger check rules.

Study reports state their headline numbers in markdown results tables
with rounded values. This module parses those tables and compares the
stated numbers against the trial ledger within the rounding tolerance
implied by the stated precision. A value that cannot be located is
UNVERIFIED, never PASS; a value that disagrees beyond rounding is FAIL.

Table shapes differ by design (lead-lag, mean comparison, event-study
CAR, cross-section), so the column mapping is per table type and the
row-label mapping is per study — both explicit in REPORT_RULES below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Special ledger-field codes used in column mappings.
HOLM_FIELD = "@holm"  # adjusted p-value from metrics["holm"] for this test
WINDOW_N_FIELD = "@window_n"  # "total (window / non-window)" observation counts
BOOT_CI_FIELD = "@boot_ci"  # "[lower, upper]" bootstrap confidence interval

_MISSING_CELLS = {"—", "--", "-", "", "n/a", "NA"}


@dataclass(frozen=True)
class MarkdownTable:
    """One markdown table: header cells and body rows (cell text, stripped)."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ReportRule:
    """One report-ledger assertion: a table row matched against a ledger test.

    ``table_headers`` identifies the table: every listed header cell must
    appear in the table's header row. ``row_label`` is a regex matched
    against the row's first cell. ``columns`` maps header cells to ledger
    test fields (or a special field code); columns not listed are ignored.
    """

    trial_id: str
    test_name: str
    table_headers: tuple[str, ...]
    row_label: str
    columns: tuple[tuple[str, str], ...]


# Column mappings per table type. Header cells are matched exactly after
# stripping; the "reject" and "leg" columns carry no checkable number.
LEAD_LAG_COLUMNS: tuple[tuple[str, str], ...] = (
    ("n", "observations"),
    ("coef", "coefficient"),
    ("SE", "standard_error"),
    ("t", "t_statistic"),
    ("raw p", "p_value"),
    ("Holm-adj p", HOLM_FIELD),
    ("Holm p", HOLM_FIELD),
    ("partial R²", "partial_r_squared"),
    ("incr R²", "incremental_r_squared"),
)

MEAN_COMPARISON_COLUMNS: tuple[tuple[str, str], ...] = (
    ("n (window / non-window)", WINDOW_N_FIELD),
    ("mean |r| window", "mean_window"),
    ("mean |r| non-window", "mean_nonwindow"),
    ("mean diff", "coefficient"),
    ("SE", "standard_error"),
    ("t", "t_statistic"),
    ("raw p", "p_value"),
    ("Holm-adj p", HOLM_FIELD),
    ("ratio", "effect_ratio"),
    ("95% boot CI", BOOT_CI_FIELD),
)

CAR_COLUMNS: tuple[tuple[str, str], ...] = (
    ("mean CAR", "coefficient"),
    ("SE", "standard_error"),
    ("z", "t_statistic"),
    ("raw p", "p_value"),
    ("Holm p", HOLM_FIELD),
    ("std. mean CAR", "standardized_mean_car"),
)

CROSS_SECTION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("slope", "coefficient"),
    ("SE", "standard_error"),
    ("t", "t_statistic"),
    ("raw p", "p_value"),
    ("Holm p", HOLM_FIELD),
    ("R²", "r_squared"),
)

_LEAD_LAG_HEADERS = ("Holm-adj p", "partial R²")
_LEAD_LAG_HEADERS_007 = ("Holm p", "partial R²")
_MEAN_HEADERS = ("mean |r| window", "ratio")
_CAR_HEADERS = ("mean CAR", "std. mean CAR")
_CROSS_HEADERS = ("slope", "R²")


def _rule(
    trial_id: str,
    test_name: str,
    headers: tuple[str, ...],
    label: str,
    columns: tuple[tuple[str, str], ...],
) -> ReportRule:
    return ReportRule(
        trial_id=trial_id,
        test_name=test_name,
        table_headers=headers,
        row_label=label,
        columns=columns,
    )


# Per-study report rules, keyed by study directory slug. Row labels are
# regexes matched against the first cell of the results-table row; the
# label text is quoted from the report, not guessed.
REPORT_RULES: dict[str, tuple[ReportRule, ...]] = {
    "btc-eth-001": (
        _rule("T0001", "daily_btc_eth", _LEAD_LAG_HEADERS,
              r"\(a\) daily BTC→ETH, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0001", "daily_btc_eth_no_factor", _LEAD_LAG_HEADERS,
              r"\(a\) no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0001", "daily_btc_sol", _LEAD_LAG_HEADERS,
              r"\(b\) daily BTC→SOL, ETH control", LEAD_LAG_COLUMNS),
        _rule("T0001", "daily_btc_sol_no_factor", _LEAD_LAG_HEADERS,
              r"\(b\) no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0001", "hourly_btc_eth", _LEAD_LAG_HEADERS,
              r"\(c\) 1H BTC→ETH, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0001", "hourly_btc_eth_no_factor", _LEAD_LAG_HEADERS,
              r"\(c\) no-factor control", LEAD_LAG_COLUMNS),
    ),
    "lowvol-002": (
        _rule("T0002", "daily_btc_sol_interaction", _LEAD_LAG_HEADERS,
              r"A1 daily BTC→SOL interaction, ETH control", LEAD_LAG_COLUMNS),
        _rule("T0002", "daily_btc_sol_interaction_no_factor", _LEAD_LAG_HEADERS,
              r"A1 no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0002", "daily_btc_sol_lowvol", _LEAD_LAG_HEADERS,
              r"A2 daily BTC→SOL low-vol subsample, ETH control", LEAD_LAG_COLUMNS),
        _rule("T0002", "daily_btc_sol_lowvol_no_factor", _LEAD_LAG_HEADERS,
              r"A2 no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0002", "hourly_btc_eth_interaction", _LEAD_LAG_HEADERS,
              r"B1 1H BTC→ETH interaction, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0002", "hourly_btc_eth_interaction_no_factor", _LEAD_LAG_HEADERS,
              r"B1 no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0002", "hourly_btc_eth_lowvol", _LEAD_LAG_HEADERS,
              r"B2 1H BTC→ETH low-vol subsample, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0002", "hourly_btc_eth_lowvol_no_factor", _LEAD_LAG_HEADERS,
              r"B2 no-factor control", LEAD_LAG_COLUMNS),
    ),
    "move-vix-003": (
        _rule("T0004", "daily_tyvix_vix", _LEAD_LAG_HEADERS,
              r"\(a\) daily TYVIX→VIX, SPX control", LEAD_LAG_COLUMNS),
        _rule("T0004", "daily_tyvix_vix_no_factor", _LEAD_LAG_HEADERS,
              r"\(a\) no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0004", "daily_tyvix_vxn", _LEAD_LAG_HEADERS,
              r"\(b\) daily TYVIX→VXN, SPX control", LEAD_LAG_COLUMNS),
        _rule("T0004", "daily_tyvix_vxn_no_factor", _LEAD_LAG_HEADERS,
              r"\(b\) no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0004", "weekly_tyvix_vix", _LEAD_LAG_HEADERS,
              r"\(c\) weekly TYVIX→VIX, SPX control", LEAD_LAG_COLUMNS),
        _rule("T0004", "weekly_tyvix_vix_no_factor", _LEAD_LAG_HEADERS,
              r"\(c\) no-factor control", LEAD_LAG_COLUMNS),
    ),
    "options-expiry-004": (
        _rule("T0005", "daily_btc_eth_interaction", _LEAD_LAG_HEADERS,
              r"A daily BTC→ETH interaction, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0005", "daily_btc_eth_interaction_no_factor", _LEAD_LAG_HEADERS,
              r"A no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0005", "daily_btc_eth_window", _LEAD_LAG_HEADERS,
              r"B daily BTC→ETH window subsample, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0005", "daily_btc_eth_window_no_factor", _LEAD_LAG_HEADERS,
              r"B no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0005", "hourly_btc_eth_interaction", _LEAD_LAG_HEADERS,
              r"C 1H BTC→ETH interaction, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0005", "hourly_btc_eth_interaction_no_factor", _LEAD_LAG_HEADERS,
              r"C no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0007", "btc_mean_abs_return_comparison", _MEAN_HEADERS,
              r"\(a\) BTC", MEAN_COMPARISON_COLUMNS),
        _rule("T0007", "eth_mean_abs_return_comparison", _MEAN_HEADERS,
              r"\(b\) ETH", MEAN_COMPARISON_COLUMNS),
    ),
    "fomc-event-study-005": (
        _rule("T0010", "vix_car", _CAR_HEADERS,
              r"vix_car \(primary, one-sided < 0\)", CAR_COLUMNS),
        _rule("T0010", "spx_car", _CAR_HEADERS,
              r"spx_car \(two-sided\)", CAR_COLUMNS),
        _rule("T0010", "dgs10_car", _CAR_HEADERS,
              r"dgs10_car \(two-sided\)", CAR_COLUMNS),
        _rule("T0010", "baa10y_car", _CAR_HEADERS,
              r"baa10y_car \(two-sided\)", CAR_COLUMNS),
        _rule("T0010", "tyvix_car", _CAR_HEADERS,
              r"tyvix_car \(one-sided < 0\)", CAR_COLUMNS),
        _rule("T0009", "spx_on_dgs10", _CROSS_HEADERS,
              r"spx_on_dgs10 \(primary, one-sided < 0\)", CROSS_SECTION_COLUMNS),
        _rule("T0009", "vix_on_dgs10", _CROSS_HEADERS,
              r"vix_on_dgs10 \(two-sided\)", CROSS_SECTION_COLUMNS),
        _rule("T0009", "baa10y_on_dgs10", _CROSS_HEADERS,
              r"baa10y_on_dgs10 \(two-sided\)", CROSS_SECTION_COLUMNS),
    ),
    "macro-windows-006": (
        _rule("T0011", "daily_btc_eth_interaction", _LEAD_LAG_HEADERS,
              r"A daily BTC→ETH interaction, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0011", "daily_btc_eth_interaction_no_factor", _LEAD_LAG_HEADERS,
              r"A no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0011", "daily_btc_eth_window", _LEAD_LAG_HEADERS,
              r"B daily BTC→ETH window subsample, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0011", "daily_btc_eth_window_no_factor", _LEAD_LAG_HEADERS,
              r"B no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0011", "hourly_btc_eth_interaction", _LEAD_LAG_HEADERS,
              r"C 1H BTC→ETH interaction, SOL control", LEAD_LAG_COLUMNS),
        _rule("T0011", "hourly_btc_eth_interaction_no_factor", _LEAD_LAG_HEADERS,
              r"C no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0012", "btc_mean_abs_return_comparison", _MEAN_HEADERS,
              r"\(a\) BTC", MEAN_COMPARISON_COLUMNS),
        _rule("T0012", "eth_mean_abs_return_comparison", _MEAN_HEADERS,
              r"\(b\) ETH", MEAN_COMPARISON_COLUMNS),
    ),
    "publication-lag-007": (
        _rule("T0013", "tyvix_lagged_car", _CAR_HEADERS,
              r"tyvix_lagged_car \(primary, one-sided < 0\)", CAR_COLUMNS),
        _rule("T0013", "vix_lagged_car", _CAR_HEADERS,
              r"vix_lagged_car \(one-sided < 0\)", CAR_COLUMNS),
        _rule("T0013", "dgs10_lagged_car", _CAR_HEADERS,
              r"dgs10_lagged_car \(two-sided\)", CAR_COLUMNS),
        _rule("T0013", "baa10y_lagged_car", _CAR_HEADERS,
              r"baa10y_lagged_car \(two-sided\)", CAR_COLUMNS),
        _rule("T0013", "spx_car", _CAR_HEADERS,
              r"spx_car \(two-sided, unlagged control\)", CAR_COLUMNS),
        _rule("T0015", "spx_daily", _LEAD_LAG_HEADERS_007,
              r"spx_daily \(primary\)", LEAD_LAG_COLUMNS),
        _rule("T0015", "spx_release_day", _LEAD_LAG_HEADERS_007,
              r"spx_release_day", LEAD_LAG_COLUMNS),
        _rule("T0015", "btc_daily", _LEAD_LAG_HEADERS_007,
              r"btc_daily", LEAD_LAG_COLUMNS),
    ),
    "credit-spread-spx-008": (
        _rule("T0016", "daily_baa10y_spx", _LEAD_LAG_HEADERS,
              r"daily BAA10Y→SPX, VIX control \(primary\)", LEAD_LAG_COLUMNS),
        _rule("T0016", "daily_baa10y_spx_no_factor", _LEAD_LAG_HEADERS,
              r"no-factor control", LEAD_LAG_COLUMNS),
        _rule("T0016", "daily_baa10y_spx_naive", _LEAD_LAG_HEADERS,
              r"naive \(unlagged\) alignment", LEAD_LAG_COLUMNS),
        _rule("T0016", "daily_spx_baa10y_reverse", _LEAD_LAG_HEADERS,
              r"reverse placebo \(SPX→BAA10Y\)", LEAD_LAG_COLUMNS),
    ),
}


def _split_row(line: str) -> tuple[str, ...]:
    """Split a markdown table row on unescaped pipes, unescaping \\|."""
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return tuple(cell.replace("\\|", "|").strip() for cell in cells)


def _is_separator(line: str) -> bool:
    stripped = line.strip().strip("|")
    return bool(stripped) and all(
        char in "-: " for cell in stripped.split("|") for char in cell
    )


def parse_markdown_tables(text: str) -> tuple[MarkdownTable, ...]:
    """Extract every markdown table from the text, in document order."""
    tables: list[MarkdownTable] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            line.strip().startswith("|")
            and index + 1 < len(lines)
            and _is_separator(lines[index + 1])
        ):
            headers = _split_row(line)
            rows: list[tuple[str, ...]] = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_split_row(lines[index]))
                index += 1
            tables.append(MarkdownTable(headers=headers, rows=tuple(rows)))
            continue
        index += 1
    return tuple(tables)


def find_table(
    tables: tuple[MarkdownTable, ...],
    required_headers: tuple[str, ...],
) -> MarkdownTable | None:
    """Return the first table whose header contains every required cell."""
    for table in tables:
        if all(header in table.headers for header in required_headers):
            return table
    return None


def _rounding_tolerance(text: str) -> float:
    """The rounding tolerance implied by a report number's precision.

    A plain decimal with d digits after the point may be off by half a
    unit in the last place; a scientific-notation mantissa with d digits
    scales that half-unit by the exponent. A small absolute floor covers
    float noise.
    """
    cleaned = text.strip().lstrip("+-").replace(",", "")
    if "e" in cleaned or "E" in cleaned:
        mantissa, _, exponent = cleaned.replace("E", "e").partition("e")
        decimals = len(mantissa.partition(".")[2]) if "." in mantissa else 0
        return 0.5 * (10.0 ** (-decimals)) * (10.0 ** int(exponent)) + 1e-12
    if "." in cleaned:
        decimals = len(cleaned.partition(".")[2])
        return 0.5 * (10.0 ** (-decimals)) + 1e-12
    return 0.0  # integers must match exactly


def parse_report_number(cell: str) -> tuple[float, float] | None:
    """Parse a report table cell into (value, rounding tolerance).

    Returns None for non-numeric cells (missing markers, yes/no, text).
    Normalizes the Unicode minus sign, leading plus signs and thousands
    separators before parsing.
    """
    cleaned = cell.strip().replace("−", "-").replace(",", "")
    if cleaned in _MISSING_CELLS or cleaned.startswith("**"):
        return None
    cleaned = cleaned.lstrip("+")
    try:
        return float(cleaned), _rounding_tolerance(cleaned)
    except ValueError:
        return None


def parse_window_n(cell: str) -> tuple[int, int, int] | None:
    """Parse a 'total (window / non-window)' observation cell."""
    match = re.fullmatch(
        r"\s*([0-9,]+)\s*\(\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\)\s*",
        cell.strip(),
    )
    if match is None:
        return None
    total, window, nonwindow = (
        int(group.replace(",", "")) for group in match.groups()
    )
    return total, window, nonwindow


def parse_boot_ci(cell: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Parse a '[lower, upper]' bootstrap-CI cell into ((value, tol), ...)."""
    match = re.fullmatch(
        r"\s*\[\s*([^,\]]+)\s*,\s*([^\]]+)\s*\]\s*",
        cell.strip(),
    )
    if match is None:
        return None
    lower = parse_report_number(match.group(1))
    upper = parse_report_number(match.group(2))
    if lower is None or upper is None:
        return None
    return lower, upper
