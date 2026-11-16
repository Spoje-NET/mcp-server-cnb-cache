"""Thin HTTP client for the cnb-cache web interface."""

from __future__ import annotations

import html
import os
import re
from datetime import date as Date
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_URL = "http://localhost/cnb-cache/"
MAX_RESPONSE_BYTES = 256 * 1024
_CODE_RE = re.compile(r"^[A-Za-z]{3}$")


class CnbCacheError(Exception):
    """Actionable error; never contains credentials or raw headers."""


def normalize_base_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CnbCacheError(
            "CNB_CACHE_URL must be an absolute http(s) URL, e.g. http://localhost/cnb-cache/"
        )
    return url if url.endswith("/") else url + "/"


def validate_code(code: str) -> str:
    code = (code or "").strip().upper()
    if not _CODE_RE.match(code):
        raise CnbCacheError(f"Invalid currency code {code!r}: expected 3 letters, e.g. EUR")
    return code


class CnbCacheClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url or os.environ.get("CNB_CACHE_URL") or DEFAULT_URL)
        self.timeout = float(os.environ.get("CNB_CACHE_TIMEOUT", timeout))
        self._transport = transport

    def _get(self, params: dict[str, Any]) -> httpx.Response:
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport, follow_redirects=True
            ) as c:
                r = c.get(self.base_url, params=params)
        except httpx.HTTPError as exc:
            raise CnbCacheError(
                f"cnb-cache at {self.base_url} is unreachable ({type(exc).__name__}); "
                "check CNB_CACHE_URL"
            ) from None
        if len(r.content) > MAX_RESPONSE_BYTES:
            raise CnbCacheError("cnb-cache response too large")
        return r

    def rate(
        self,
        currency: str,
        date: str | None = None,
        age: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"currency": validate_code(currency)}
        if date:
            try:
                Date.fromisoformat(date)
            except ValueError:
                raise CnbCacheError(f"Invalid date {date!r}: expected YYYY-MM-DD") from None
            params["date"] = date
        elif age:
            params["age"] = int(age)
        r = self._get(params)
        if r.status_code != 200:
            raise CnbCacheError(f"cnb-cache returned HTTP {r.status_code} for {params['currency']}")
        try:
            data = r.json()
        except ValueError:
            raise CnbCacheError("cnb-cache returned a non-JSON response") from None
        if not isinstance(data, dict) or "rate" not in data:
            raise CnbCacheError(
                f"No rate available for {params['currency']} on the requested day "
                "(weekend/holiday, or currency not cached)"
            )
        return data

    def currencies(self) -> list[str]:
        """The index page (HTTP 404 by design) lists cached currency codes."""
        r = self._get({})
        codes = re.findall(r"\?currency=([A-Za-z]{3})\"", html.unescape(r.text))
        return sorted(dict.fromkeys(c.upper() for c in codes))
