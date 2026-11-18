"""Thin fetch layer for the evidence analyst (Stage 6b).

One function: a single HTTP request, no retries, no paging, no
clock reads. The probe script is the only caller; tests never
import this module (a test asserts the checks module does not
import it). A failed request is a result, not an exception: the
outcome records the HTTP status when there is one, or the error
type when the request failed before a response, so the report can
state exactly what happened.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Annotated

from pydantic import Field

from myquant.contracts import StrictContract


class FetchOutcome(StrictContract):
    """The result of one probe request.

    ``status`` is the HTTP status code when the server answered
    (including error codes such as 403); ``error`` names the
    failure when no response arrived (``HTTPError`` is converted
    to a status, so ``error`` covers URLError, timeouts and socket
    errors). ``payload`` is empty when no response arrived.
    """

    url: Annotated[str, Field(min_length=1)]
    method: Annotated[str, Field(min_length=1)]
    status: Annotated[int, Field(ge=100, le=599)] | None
    payload: bytes = b""
    error: str | None = None


def fetch_once(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    user_agent: str | None = None,
    timeout_seconds: float = 30.0,
) -> FetchOutcome:
    """Make one HTTP request and return its outcome.

    ``user_agent`` of None sends no User-Agent header (urllib's
    default applies — this is what FRED's edge accepts). A POST
    body is sent as JSON. No retries: a failure is recorded, not
    retried.
    """
    headers: dict[str, str] = {}
    if user_agent is not None:
        headers["User-Agent"] = user_agent
    if method == "POST":
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return FetchOutcome(
                url=url,
                method=method,
                status=response.status,
                payload=bytes(response.read()),
            )
    except urllib.error.HTTPError as exc:
        # The server answered with an error status: record the
        # status (the body is an error page, not evidence).
        return FetchOutcome(
            url=url, method=method, status=exc.code, error=f"HTTPError {exc.code}"
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return FetchOutcome(
            url=url,
            method=method,
            status=None,
            error=f"{type(exc).__name__}: {exc}",
        )
