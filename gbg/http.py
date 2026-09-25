"""Byte downloads through an injectable transport.

Trimmed from auto-zettel-skill's ``zettel_lib/http.py``: same ``Transport``
protocol and ``CassetteTransport`` test double, so fetch logic is tested
without the network, but stdlib-only (``urllib``) because all this repo ever
does is GET pinned files. There is no JSON API client here on purpose: the
GitHub API answers 403 from the cloud sandbox, so nothing may depend on it.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

DEFAULT_TIMEOUT = 120
USER_AGENT = "greek-bible-graph/0.1 (+https://github.com/nathanwdavis/greek-bible-graph)"


@dataclass
class Response:
    status: int
    content: bytes


class Transport(Protocol):
    def __call__(self, url: str) -> Response: ...


class NetworkUnavailable(RuntimeError):
    """No response at all -- as opposed to a response that says no."""


def urllib_transport(url: str) -> Response:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return Response(resp.status, resp.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read() or b"")
    except (urllib.error.URLError, OSError) as exc:
        raise NetworkUnavailable(str(exc)) from exc


class CassetteTransport:
    """Replays canned responses keyed by URL substring (test double)."""

    def __init__(self, cassettes: dict[str, Response]):
        self.cassettes = cassettes
        self.calls: list[str] = []

    def __call__(self, url: str) -> Response:
        self.calls.append(url)
        for fragment, response in self.cassettes.items():
            if fragment in url:
                return response
        raise NetworkUnavailable(f"no cassette for {url}")
