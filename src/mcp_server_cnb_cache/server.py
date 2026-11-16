"""MCP server: Czech National Bank exchange rates from a cnb-cache instance."""

from __future__ import annotations

import argparse
import os
from datetime import date as Date
from datetime import timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__
from .client import CnbCacheClient, CnbCacheError, validate_code

# Every tool here only reads from cnb-cache, so the read-only mode
# (CNB_CACHE_READ_ONLY) has nothing to hide; the variable is accepted for
# mcprack uniformity.
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)

MAX_HISTORY_DAYS = 31

mcp = FastMCP(
    "mcp-server-cnb-cache",
    version=__version__,
    instructions=(
        "Czech National Bank (CNB) daily exchange rates served by a cnb-cache instance. "
        "Rates are expressed in CZK per `amount` units of the foreign currency "
        "(e.g. JPY is quoted per 100). CNB publishes no rates on weekends/holidays."
    ),
)

_client: CnbCacheClient | None = None


def client() -> CnbCacheClient:
    global _client
    if _client is None:
        _client = CnbCacheClient()
    return _client


def _per_unit(info: dict[str, Any]) -> float:
    return float(info["rate"]) / float(info.get("amount") or 1)


@mcp.tool(
    title="Get Exchange Rate",
    description="Get the CNB exchange rate (CZK per `amount` units) of one currency for a given day.",
    annotations=READ_ONLY_ANNOTATIONS,
)
def get_rate(
    currency: Annotated[str, Field(description="ISO 4217 code, e.g. EUR, USD", min_length=3, max_length=3)],
    date: Annotated[str | None, Field(description="Day as YYYY-MM-DD (default: today)")] = None,
    age: Annotated[int | None, Field(description="Days back from today; ignored if date is given", ge=0, le=3650)] = None,
) -> dict[str, Any]:
    try:
        return client().rate(currency, date, age)
    except CnbCacheError as exc:
        raise ValueError(str(exc)) from None


@mcp.tool(
    title="List Cached Currencies",
    description="List the currency codes that the cnb-cache instance keeps.",
    annotations=READ_ONLY_ANNOTATIONS,
)
def list_currencies() -> list[str]:
    try:
        return client().currencies()
    except CnbCacheError as exc:
        raise ValueError(str(exc)) from None


@mcp.tool(
    title="Convert Amount",
    description="Convert an amount between CZK and a foreign currency (or two foreign currencies via CZK) using CNB rates of a given day.",
    annotations=READ_ONLY_ANNOTATIONS,
)
def convert_amount(
    amount: Annotated[float, Field(description="Amount in the source currency")],
    from_currency: Annotated[str, Field(description="Source code, e.g. CZK, EUR", min_length=3, max_length=3)],
    to_currency: Annotated[str, Field(description="Target code, e.g. CZK, EUR", min_length=3, max_length=3)],
    date: Annotated[str | None, Field(description="Day as YYYY-MM-DD (default: today)")] = None,
) -> dict[str, Any]:
    try:
        src, dst = validate_code(from_currency), validate_code(to_currency)

        def czk_per_unit(code: str) -> float:
            return 1.0 if code == "CZK" else _per_unit(client().rate(code, date))

        result = amount * czk_per_unit(src) / czk_per_unit(dst)
        return {
            "amount": amount,
            "from": src,
            "to": dst,
            "date": date or Date.today().isoformat(),
            "result": round(result, 4),
        }
    except CnbCacheError as exc:
        raise ValueError(str(exc)) from None


@mcp.tool(
    title="Get Rate History",
    description=f"Get daily CNB rates of one currency over a date range (max {MAX_HISTORY_DAYS} days). Days without a published rate are skipped.",
    annotations=READ_ONLY_ANNOTATIONS,
)
def get_rate_history(
    currency: Annotated[str, Field(description="ISO 4217 code, e.g. EUR", min_length=3, max_length=3)],
    from_date: Annotated[str, Field(description="First day, YYYY-MM-DD")],
    to_date: Annotated[str | None, Field(description="Last day, YYYY-MM-DD (default: today)")] = None,
) -> dict[str, Any]:
    try:
        start = Date.fromisoformat(from_date)
        end = Date.fromisoformat(to_date) if to_date else Date.today()
    except ValueError:
        raise ValueError("Dates must be in YYYY-MM-DD format") from None
    if end < start:
        raise ValueError("to_date must not be before from_date")
    if (end - start).days + 1 > MAX_HISTORY_DAYS:
        raise ValueError(f"Range too long: at most {MAX_HISTORY_DAYS} days")
    rates, skipped = [], []
    day = start
    while day <= end:
        try:
            rates.append(client().rate(currency, day.isoformat()))
        except CnbCacheError as exc:
            if "unreachable" in str(exc):
                raise ValueError(str(exc)) from None
            skipped.append(day.isoformat())
        day += timedelta(days=1)
    return {"currency": validate_code(currency), "rates": rates, "skipped_days": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-server-cnb-cache",
        description="MCP server for CNB exchange rates (stdio). "
        "Configure with CNB_CACHE_URL (default http://localhost/cnb-cache/).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    mcp.run(transport=os.environ.get("CNB_CACHE_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
