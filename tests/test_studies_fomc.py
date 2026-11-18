"""Tests for the FOMC meeting calendar module (offline fixtures only).

The heading fixtures are the real <h5> headings from the Fed's
fomchistorical pages for 2003, 2008, 2012, 2013, 2017 and 2020
(fetched 2026-11-18); the calendar fixture mirrors the
fomccalendars.htm markup for the 2024 section and the 2025
notation-vote row.
"""

from __future__ import annotations

from datetime import date

import pytest

from myquant.studies.fomc import (
    FOMCMeetingKind,
    annual_counts,
    excluded_meetings,
    merge_consecutive_meetings,
    parse_calendar_page,
    parse_historical_heading,
    parse_historical_page,
    scheduled_meetings,
    statement_dates,
)

HEADINGS_2003 = (
    "January 28-29 Meeting - 2003",
    "March 18 Meeting - 2003",
    "March 25 Conference Call - 2003",
    "April 1 Conference Call - 2003",
    "April 8 Conference Call - 2003",
    "April 16 Conference Call - 2003",
    "May 6 Meeting - 2003",
    "June 24-25 Meeting - 2003",
    "August 12 Meeting - 2003",
    "September 15 Meeting - 2003",
    "September 16 Meeting - 2003",
    "October 28 Meeting - 2003",
    "December 9 Meeting - 2003",
)

HEADINGS_2008 = (
    "January 9 Conference Call - 2008",
    "January 21 Conference Call - 2008",
    "January 29-30 Meeting - 2008",
    "March 10 Conference Call - 2008",
    "March 18 Meeting - 2008",
    "April 29-30 Meeting - 2008",
    "June 24-25 Meeting - 2008",
    "July 24 Conference Call - 2008",
    "August 5 Meeting - 2008",
    "September 16 Meeting - 2008",
    "September 29 Conference Call - 2008",
    "October 7 Conference Call - 2008",
    "October 28-29 Meeting - 2008",
    "December 15-16 Meeting - 2008",
)

HEADINGS_2020 = (
    "January 28-29 Meeting - 2020",
    "March 2 (unscheduled) Meeting - 2020",
    "March 15 (unscheduled) Meeting - 2020",
    "March 17-18 (cancelled) Meeting - 2020",
    "March 19 (notation vote) - 2020",
    "March 23 (notation vote) - 2020",
    "March 31 (notation vote) - 2020",
    "April 28-29 Meeting - 2020",
    "June 9-10 Meeting - 2020",
    "July 28-29 Meeting - 2020",
    "August 27 (notation vote) - 2020",
    "September 15-16 Meeting - 2020",
    "November 4-5 Meeting - 2020",
    "December 15-16 Meeting - 2020",
)

# 2012 spells the cross-month meeting out: "July 31-August 1  Meeting"
# (note the double space before "Meeting").
HEADINGS_2012 = (
    "January 24-25 Meeting - 2012",
    "March 13 Meeting - 2012",
    "April 24-25 Meeting - 2012",
    "June 19-20 Meeting - 2012",
    "July 31-August 1  Meeting - 2012",
    "September 12-13 Meeting - 2012",
    "October 23-24 Meeting - 2012",
    "December 11-12 Meeting - 2012",
)

# 2017 uses the slash spelling with abbreviated months, twice.
HEADINGS_2017 = (
    "Jan/Feb 31-1 Meeting - 2017",
    "March 14-15 Meeting - 2017",
    "May 2-3 Meeting - 2017",
    "June 13-14 Meeting - 2017",
    "July 25-26 Meeting - 2017",
    "September 19-20 Meeting - 2017",
    "Oct/Nov 31-1 Meeting - 2017",
    "December 12-13 Meeting - 2017",
)

# 2013 has a slash cross-month meeting and an unscheduled entry with
# no "Meeting" word at all.
HEADINGS_2013 = (
    "January 29-30 Meeting - 2013",
    "March 19-20 Meeting - 2013",
    "April/May 30-1 Meeting - 2013",
    "June 18-19 Meeting - 2013",
    "July 30-31 Meeting - 2013",
    "September 17-18 Meeting - 2013",
    "October 16 (unscheduled) - 2013",
    "October 29-30 Meeting - 2013",
    "December 17-18 Meeting - 2013",
)

CALENDAR_2024_SECTION = """
<div class="panel panel-default">
    <div class="panel-heading"><h4><a id="42828">2024 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting" ">
    <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>January</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">30-31</div>
</div>
<div class="fomc-meeting--shaded row fomc-meeting" ">
    <div class="fomc-meeting--shaded fomc-meeting__month"><strong>March</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">19-20*</div>
</div>
<div class="row fomc-meeting" ">
    <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>Apr/May</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">30-1</div>
</div>
<div class="fomc-meeting--shaded row fomc-meeting" ">
    <div class="fomc-meeting--shaded fomc-meeting__month"><strong>June</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">11-12*</div>
</div>
<div class="row fomc-meeting" ">
    <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>July</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">30-31</div>
</div>
<div class="fomc-meeting--shaded row fomc-meeting" ">
    <div class="fomc-meeting--shaded fomc-meeting__month"><strong>September</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">17-18*</div>
</div>
<div class="row fomc-meeting" ">
    <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>November</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">6-7</div>
</div>
<div class="fomc-meeting--shaded row fomc-meeting" ">
    <div class="fomc-meeting--shaded fomc-meeting__month"><strong>December</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">17-18*</div>
</div>
</div>
"""

CALENDAR_2025_NOTATION_VOTE = """
<div class="panel panel-default">
    <div class="panel-heading"><h4><a id="42829">2025 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting" ">
    <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>July</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">29-30</div>
</div>
<div class="fomc-meeting--shaded row fomc-meeting" ">
    <div class="fomc-meeting--shaded fomc-meeting__month"><strong>August</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">22 (notation vote)</div>
</div>
<div class="row fomc-meeting" ">
    <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>September</strong></div>
    <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">16-17*</div>
</div>
</div>
"""


def _headings_page(headings: tuple[str, ...]) -> str:
    body = "".join(f"<h5>{heading}</h5>\n" for heading in headings)
    return f"<html><body>\n{body}</body></html>\n"


def test_parse_2003_headings_merges_split_september_meeting() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2003), 2003)
    assert len(meetings) == 13
    merged, merges = merge_consecutive_meetings(meetings)
    assert merges == ((date(2003, 9, 15), date(2003, 9, 16)),)
    scheduled = scheduled_meetings(merged)
    assert len(scheduled) == 8
    assert statement_dates(merged) == (
        date(2003, 1, 29),
        date(2003, 3, 18),
        date(2003, 5, 6),
        date(2003, 6, 25),
        date(2003, 8, 12),
        date(2003, 9, 16),
        date(2003, 10, 28),
        date(2003, 12, 9),
    )
    # The four conference calls are recorded as excluded, not dropped.
    excluded = excluded_meetings(merged)
    assert len(excluded) == 4
    assert all(
        meeting.kind is FOMCMeetingKind.CONFERENCE_CALL for meeting in excluded
    )


def test_parse_2008_headings_exclude_emergency_conference_calls() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2008), 2008)
    merged, merges = merge_consecutive_meetings(meetings)
    assert merges == ()
    scheduled = scheduled_meetings(merged)
    assert len(scheduled) == 8
    statements = statement_dates(merged)
    assert date(2008, 12, 16) in statements
    # The emergency actions were decided on conference calls (Jan 21,
    # Mar 10, Oct 7) and their announcement dates never enter the
    # scheduled list.
    assert date(2008, 1, 22) not in statements
    assert date(2008, 3, 16) not in statements
    assert date(2008, 10, 8) not in statements
    excluded = excluded_meetings(merged)
    assert len(excluded) == 6
    assert {meeting.start_date for meeting in excluded} == {
        date(2008, 1, 9),
        date(2008, 1, 21),
        date(2008, 3, 10),
        date(2008, 7, 24),
        date(2008, 9, 29),
        date(2008, 10, 7),
    }


def test_parse_2020_headings_seven_scheduled_and_exclusions() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2020), 2020)
    merged, merges = merge_consecutive_meetings(meetings)
    assert merges == ()
    scheduled = scheduled_meetings(merged)
    assert len(scheduled) == 7
    assert statement_dates(merged) == (
        date(2020, 1, 29),
        date(2020, 4, 29),
        date(2020, 6, 10),
        date(2020, 7, 29),
        date(2020, 9, 16),
        date(2020, 11, 5),
        date(2020, 12, 16),
    )
    excluded = excluded_meetings(merged)
    assert len(excluded) == 7
    kinds = sorted(meeting.kind.value for meeting in excluded)
    assert kinds == [
        "cancelled",
        "notation_vote",
        "notation_vote",
        "notation_vote",
        "notation_vote",
        "unscheduled",
        "unscheduled",
    ]
    assert date(2020, 3, 15) not in statement_dates(merged)
    assert date(2020, 3, 3) not in statement_dates(merged)


def test_parse_2012_headings_spelled_cross_month() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2012), 2012)
    assert len(meetings) == 8
    assert all(
        meeting.kind is FOMCMeetingKind.SCHEDULED for meeting in meetings
    )
    assert statement_dates(meetings) == (
        date(2012, 1, 25),
        date(2012, 3, 13),
        date(2012, 4, 25),
        date(2012, 6, 20),
        date(2012, 8, 1),
        date(2012, 9, 13),
        date(2012, 10, 24),
        date(2012, 12, 12),
    )


def test_parse_2017_headings_slash_cross_month_abbreviated() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2017), 2017)
    assert len(meetings) == 8
    assert all(
        meeting.kind is FOMCMeetingKind.SCHEDULED for meeting in meetings
    )
    assert statement_dates(meetings) == (
        date(2017, 2, 1),
        date(2017, 3, 15),
        date(2017, 5, 3),
        date(2017, 6, 14),
        date(2017, 7, 26),
        date(2017, 9, 20),
        date(2017, 11, 1),
        date(2017, 12, 13),
    )


def test_parse_2013_headings_slash_cross_month_and_unscheduled() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2013), 2013)
    merged, merges = merge_consecutive_meetings(meetings)
    assert merges == ()
    scheduled = scheduled_meetings(merged)
    assert len(scheduled) == 8
    assert statement_dates(merged) == (
        date(2013, 1, 30),
        date(2013, 3, 20),
        date(2013, 5, 1),
        date(2013, 6, 19),
        date(2013, 7, 31),
        date(2013, 9, 18),
        date(2013, 10, 30),
        date(2013, 12, 18),
    )
    excluded = excluded_meetings(merged)
    assert len(excluded) == 1
    assert excluded[0].kind is FOMCMeetingKind.UNSCHEDULED
    assert excluded[0].start_date == date(2013, 10, 16)


def test_parse_historical_heading_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="unrecognized FOMC heading"):
        parse_historical_heading("Not a meeting heading", 2003)
    with pytest.raises(ValueError, match="does not match page year"):
        parse_historical_heading("January 28-29 Meeting - 2003", 2004)
    with pytest.raises(ValueError, match="runs backwards"):
        parse_historical_heading("January 29-28 Meeting - 2003", 2003)
    with pytest.raises(ValueError, match="non-consecutive months"):
        parse_historical_heading("January 29-March 1 Meeting - 2003", 2003)
    with pytest.raises(ValueError, match="invalid date"):
        parse_historical_heading("February 30 Meeting - 2003", 2003)
    with pytest.raises(ValueError, match="no <h5> headings"):
        parse_historical_page("<html><body>no headings</body></html>", 2003)


def test_parse_calendar_page_2024_cross_month_and_sep_markers() -> None:
    meetings = parse_calendar_page(CALENDAR_2024_SECTION)
    assert len(meetings) == 8
    assert all(
        meeting.kind is FOMCMeetingKind.SCHEDULED for meeting in meetings
    )
    assert statement_dates(meetings) == (
        date(2024, 1, 31),
        date(2024, 3, 20),
        date(2024, 5, 1),
        date(2024, 6, 12),
        date(2024, 7, 31),
        date(2024, 9, 18),
        date(2024, 11, 7),
        date(2024, 12, 18),
    )
    # The Apr/May cross-month meeting spans the month boundary.
    april = next(
        meeting
        for meeting in meetings
        if meeting.start_date == date(2024, 4, 30)
    )
    assert april.end_date == date(2024, 5, 1)


def test_parse_calendar_page_excludes_notation_votes() -> None:
    meetings = parse_calendar_page(CALENDAR_2025_NOTATION_VOTE)
    assert len(scheduled_meetings(meetings)) == 2
    excluded = excluded_meetings(meetings)
    assert len(excluded) == 1
    assert excluded[0].kind is FOMCMeetingKind.NOTATION_VOTE
    assert excluded[0].start_date == date(2025, 8, 22)


def test_parse_calendar_page_rejects_mismatched_divs() -> None:
    broken = CALENDAR_2024_SECTION.replace(
        '<div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">6-7</div>',
        "",
    )
    with pytest.raises(ValueError, match="month divs but"):
        parse_calendar_page(broken)
    with pytest.raises(ValueError, match="no FOMC year sections"):
        parse_calendar_page("<html><body>no sections</body></html>")


def test_merge_only_joins_consecutive_scheduled_entries() -> None:
    meetings = parse_historical_page(_headings_page(HEADINGS_2020), 2020)
    merged, merges = merge_consecutive_meetings(meetings)
    # March 2 (unscheduled) and March 15 (unscheduled) are not merged
    # with each other or with the cancelled March 17-18 meeting.
    assert merges == ()
    assert len(merged) == len(meetings)


def test_annual_counts_key_on_statement_year() -> None:
    meetings = (
        parse_historical_page(_headings_page(HEADINGS_2003), 2003)
        + parse_historical_page(_headings_page(HEADINGS_2008), 2008)
        + parse_historical_page(_headings_page(HEADINGS_2020), 2020)
    )
    merged, _ = merge_consecutive_meetings(meetings)
    assert annual_counts(merged) == {2003: 8, 2008: 8, 2020: 7}
