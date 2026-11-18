"""FOMC meeting calendar: scheduled meetings and statement dates.

The calendar comes from the Federal Reserve's own pages
(federalreserve.gov, public schedule data, no key):

- Historical pages ``fomchistorical{YYYY}.htm`` (2003-2020): ``<h5>``
  headings such as ``"January 29-30 Meeting - 2008"``,
  ``"March 10 Conference Call - 2008"``,
  ``"March 17-18 (cancelled) Meeting - 2020"`` and
  ``"August 27 (notation vote) - 2020"``.
- Calendar page ``fomccalendars.htm`` (2021 onwards): year sections
  headed ``"2026 FOMC Meetings"`` with ``fomc-meeting__month`` /
  ``fomc-meeting__date`` divs holding e.g. ``"January"`` / ``"27-28"``
  (a trailing ``*`` marks a Summary of Economic Projections meeting;
  cross-month meetings use labels such as ``"Apr/May"`` with dates
  ``"30-1"``).

Classification (from the entry text):

- **scheduled**: plain ``"Meeting"`` entries with no parenthetical
  qualifier and not a conference call. These are the eight regularly
  scheduled meetings per year (seven in 2020: the March 17-18 meeting
  was cancelled and the Committee acted at unscheduled meetings
  instead).
- **excluded**: ``"Conference Call"``, ``"(unscheduled)"``,
  ``"(cancelled)"`` and ``"(notation vote)"`` entries. Unscheduled
  actions (e.g. 2008-01-22, 2008-03-16, 2008-10-08, 2020-03-03,
  2020-03-15) were decided at conference calls or unscheduled meetings
  and never appear in the scheduled list.

Two-day meetings are sometimes listed as two consecutive single-day
headings (September 2003 appears as ``"September 15 Meeting"`` and
``"September 16 Meeting"``); consecutive-day scheduled entries are
merged into one meeting before any count or statement-date use.

**Statement day** is the last day of the meeting: the statement is
released on the second day of a two-day meeting (or the same day for a
one-day meeting), at about 14:00-14:15 ET. The event-study t=0 is the
statement day; the daily close (16:00 ET) already contains the
statement reaction.

This module is pure parsing and calendar arithmetic (no network, no
market data). Fetching and cross-checking live in the study 005 fetch
script; the verification record lives in the study manifest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class FOMCMeetingKind(StrEnum):
    """What kind of FOMC entry a page lists."""

    SCHEDULED = "scheduled"
    CONFERENCE_CALL = "conference_call"
    UNSCHEDULED = "unscheduled"
    CANCELLED = "cancelled"
    NOTATION_VOTE = "notation_vote"


@dataclass(frozen=True)
class FOMCMeeting:
    """One FOMC meeting entry: a date range plus its classification."""

    start_date: date
    end_date: date
    kind: FOMCMeetingKind
    source: str  # "historical" (fomchistorical{YYYY}.htm) or "calendar"

    @property
    def statement_date(self) -> date:
        """The statement release day: the last day of the meeting."""
        return self.end_date


_MONTH_NUMBERS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# "January 29-30 Meeting - 2008" / "March 18 Meeting - 2003" /
# "March 17-18 (cancelled) Meeting - 2020" / "August 27 (notation vote) - 2020"
# Cross-month meetings come in two spellings: "April/May 30-1 Meeting - 2013"
# (month/month day-day) and "July 31-August 1  Meeting - 2012" (the last
# month is spelled out after the dash; note the double space before "Meeting").
_HEADING_PATTERN = re.compile(
    r"^(?P<month>[A-Za-z]+(?:/[A-Za-z]+)?)\s+"
    r"(?P<first_day>\d{1,2})"
    r"(?:-(?P<last_month>[A-Za-z]+)?\s*(?P<last_day>\d{1,2}))?\s*"
    r"(?P<qualifier>\([^)]*\))?\s*"
    r"(?P<rest>.*?)\s*-\s*(?P<year>\d{4})\s*$"
)

_YEAR_SECTION_PATTERN = re.compile(
    r'<h4><a id="\d+">(?P<year>\d{4}) FOMC Meetings</a></h4>'
)
_MONTH_DIV_PATTERN = re.compile(
    r'<div class="[^"]*fomc-meeting__month[^"]*">\s*<strong>'
    r"(?P<month>[^<]+)</strong>\s*</div>"
)
_DATE_DIV_PATTERN = re.compile(
    r'<div class="[^"]*fomc-meeting__date[^"]*">(?P<date>[^<]+)</div>'
)


def _month_number(name: str) -> int:
    try:
        return _MONTH_NUMBERS[name.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unknown month name: {name!r}") from exc


def _classify_heading(qualifier: str, rest: str) -> FOMCMeetingKind:
    text = f"{qualifier} {rest}".lower()
    if "conference call" in text:
        return FOMCMeetingKind.CONFERENCE_CALL
    if "unscheduled" in text:
        return FOMCMeetingKind.UNSCHEDULED
    if "cancelled" in text:
        return FOMCMeetingKind.CANCELLED
    if "notation vote" in text:
        return FOMCMeetingKind.NOTATION_VOTE
    if "meeting" in text:
        return FOMCMeetingKind.SCHEDULED
    raise ValueError(f"cannot classify FOMC heading: {qualifier!r} {rest!r}")


def parse_historical_heading(text: str, year: int) -> FOMCMeeting:
    """Parse one ``<h5>`` heading from a fomchistorical page.

    The year is passed in (it is part of the page identity) and must
    agree with the year suffix in the heading text.
    """
    cleaned = re.sub(r"<[^>]+>", "", text).strip()
    match = _HEADING_PATTERN.match(cleaned)
    if match is None:
        raise ValueError(f"unrecognized FOMC heading: {text!r}")
    heading_year = int(match.group("year"))
    if heading_year != year:
        raise ValueError(
            f"FOMC heading year {heading_year} does not match page year {year}: "
            f"{text!r}"
        )
    month_text = match.group("month")
    if "/" in month_text:
        first_month_text, second_month_text = month_text.split("/", maxsplit=1)
    else:
        first_month_text, second_month_text = month_text, None
    first_month = _month_number(first_month_text)
    last_month_text = match.group("last_month")
    if last_month_text is not None:
        last_month = _month_number(last_month_text)
    elif second_month_text is not None:
        last_month = _month_number(second_month_text)
    else:
        last_month = first_month
    first_day = int(match.group("first_day"))
    last_day = match.group("last_day")
    last_day_int = int(last_day) if last_day is not None else first_day
    if last_month == first_month and last_day_int < first_day:
        raise ValueError(
            f"FOMC heading day range runs backwards: {text!r}"
        )
    if last_month != first_month and last_month != first_month + 1:
        raise ValueError(
            f"FOMC heading spans non-consecutive months: {text!r}"
        )
    kind = _classify_heading(
        match.group("qualifier") or "", match.group("rest")
    )
    try:
        start = date(year, first_month, first_day)
        end = date(year, last_month, last_day_int)
    except ValueError as exc:
        raise ValueError(f"FOMC heading has an invalid date: {text!r}") from exc
    return FOMCMeeting(
        start_date=start, end_date=end, kind=kind, source="historical"
    )


def parse_historical_page(html: str, year: int) -> tuple[FOMCMeeting, ...]:
    """Parse every ``<h5>`` heading of one fomchistorical page."""
    headings = re.findall(r"<h5[^>]*>(.*?)</h5>", html, flags=re.S)
    if not headings:
        raise ValueError(f"no <h5> headings found on the {year} FOMC page")
    return tuple(parse_historical_heading(heading, year) for heading in headings)


def _parse_calendar_month_date(
    month_text: str, date_text: str, year: int
) -> FOMCMeeting:
    """Parse one (month div, date div) pair from the calendar page.

    The month label is one month ("January") or two ("Apr/May") for a
    cross-month meeting; the date is "D1-D2", "D1", or "D1 (notation
    vote)". A trailing "*" marks a Summary of Economic Projections
    meeting and is stripped.
    """
    cleaned_date = date_text.strip().rstrip("*").strip()
    if "notation vote" in cleaned_date.lower():
        day_text = cleaned_date.split("(")[0].strip()
        kind = FOMCMeetingKind.NOTATION_VOTE
    else:
        day_text = cleaned_date
        kind = FOMCMeetingKind.SCHEDULED
    months = [part.strip() for part in month_text.strip().split("/")]
    if len(months) not in (1, 2):
        raise ValueError(f"unrecognized FOMC month label: {month_text!r}")
    days = [part.strip() for part in day_text.split("-")]
    if len(days) not in (1, 2):
        raise ValueError(f"unrecognized FOMC date text: {date_text!r}")
    start_month = _month_number(months[0])
    end_month = _month_number(months[1]) if len(months) == 2 else start_month
    first_day = int(days[0])
    last_day = int(days[1]) if len(days) == 2 else first_day
    if len(months) == 1 and len(days) == 2 and last_day < first_day:
        # A range that runs backwards within one month label still spans
        # into the next month (defensive; the page uses "Apr/May" labels
        # for these, but do not fail if it ever drops the second month).
        end_month = start_month + 1
        end_year = year
        if end_month == 13:
            end_month = 1
            end_year = year + 1
    else:
        end_year = year
    try:
        start = date(year, start_month, first_day)
        end = date(end_year, end_month, last_day)
    except ValueError as exc:
        raise ValueError(
            f"invalid FOMC calendar date: {month_text!r} {date_text!r} "
            f"({year})"
        ) from exc
    if end < start:
        raise ValueError(
            f"FOMC calendar meeting ends before it starts: "
            f"{month_text!r} {date_text!r} ({year})"
        )
    return FOMCMeeting(
        start_date=start, end_date=end, kind=kind, source="calendar"
    )


def parse_calendar_page(html: str) -> tuple[FOMCMeeting, ...]:
    """Parse every year section of the fomccalendars.htm page.

    Sections are keyed by the year in their heading; the page lists
    years newest-first with 2027 last, so callers must not assume order.
    """
    sections = _YEAR_SECTION_PATTERN.split(html)
    # split() yields [preamble, year, content, year, content, ...].
    if len(sections) < 3:
        raise ValueError("no FOMC year sections found on the calendar page")
    meetings: list[FOMCMeeting] = []
    for index in range(1, len(sections) - 1, 2):
        year = int(sections[index])
        content = sections[index + 1]
        months = _MONTH_DIV_PATTERN.findall(content)
        dates = _DATE_DIV_PATTERN.findall(content)
        if len(months) != len(dates):
            raise ValueError(
                f"{year} calendar section: {len(months)} month divs but "
                f"{len(dates)} date divs; refusing to guess the pairing"
            )
        for month_text, date_text in zip(months, dates, strict=True):
            meetings.append(
                _parse_calendar_month_date(month_text, date_text, year)
            )
    return tuple(meetings)


def merge_consecutive_meetings(
    meetings: tuple[FOMCMeeting, ...],
) -> tuple[tuple[FOMCMeeting, ...], tuple[tuple[date, date], ...]]:
    """Merge consecutive-day scheduled entries into one meeting.

    Some two-day meetings are listed as two single-day headings
    (September 2003: "September 15 Meeting" and "September 16
    Meeting"). Scheduled meetings are weeks apart, so two scheduled
    entries on consecutive calendar days can only be one split meeting.
    Returns the merged meetings and the list of merged (first, last)
    date pairs, for the verification record.
    """
    ordered = sorted(meetings, key=lambda item: (item.start_date, item.end_date))
    merged: list[FOMCMeeting] = []
    merges: list[tuple[date, date]] = []
    for meeting in ordered:
        if (
            merged
            and meeting.kind is FOMCMeetingKind.SCHEDULED
            and merged[-1].kind is FOMCMeetingKind.SCHEDULED
            and meeting.start_date == merged[-1].end_date + timedelta(days=1)
            and merged[-1].source == meeting.source
        ):
            previous = merged[-1]
            merged[-1] = FOMCMeeting(
                start_date=previous.start_date,
                end_date=meeting.end_date,
                kind=FOMCMeetingKind.SCHEDULED,
                source=previous.source,
            )
            merges.append((previous.start_date, meeting.end_date))
        else:
            merged.append(meeting)
    return tuple(merged), tuple(merges)


def scheduled_meetings(
    meetings: tuple[FOMCMeeting, ...],
) -> tuple[FOMCMeeting, ...]:
    """The scheduled meetings only, in date order."""
    return tuple(
        meeting
        for meeting in sorted(meetings, key=lambda item: item.start_date)
        if meeting.kind is FOMCMeetingKind.SCHEDULED
    )


def excluded_meetings(
    meetings: tuple[FOMCMeeting, ...],
) -> tuple[FOMCMeeting, ...]:
    """Everything that is not a scheduled meeting, in date order."""
    return tuple(
        meeting
        for meeting in sorted(meetings, key=lambda item: item.start_date)
        if meeting.kind is not FOMCMeetingKind.SCHEDULED
    )


def statement_dates(
    meetings: tuple[FOMCMeeting, ...],
) -> tuple[date, ...]:
    """Statement days of the scheduled meetings, in date order."""
    return tuple(
        meeting.statement_date for meeting in scheduled_meetings(meetings)
    )


def annual_counts(meetings: tuple[FOMCMeeting, ...]) -> dict[int, int]:
    """Scheduled meetings per calendar year (keyed by statement year)."""
    counts: dict[int, int] = {}
    for meeting in scheduled_meetings(meetings):
        year = meeting.statement_date.year
        counts[year] = counts.get(year, 0) + 1
    return counts
