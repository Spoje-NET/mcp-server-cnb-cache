import json

import httpx
import pytest
from fastmcp import Client

from mcp_server_cnb_cache import client as client_mod
from mcp_server_cnb_cache import server

USD = {"id": 6, "date": "2025-01-24", "currency": "dolar", "amount": 1, "code": "USD", "rate": 24.0, "age": 0}
JPY = {"id": 7, "date": "2025-01-24", "currency": "jen", "amount": 100, "code": "JPY", "rate": 15.0, "age": 0}
INDEX = '<ul><li><a href="?currency=USD">USD</a></li><li><a href="?currency=JPY">JPY</a></li></ul>'


def handler(request: httpx.Request) -> httpx.Response:
    cur = request.url.params.get("currency")
    if cur is None:
        return httpx.Response(404, text=INDEX)
    if request.url.params.get("date") == "2025-01-25":  # weekend
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={"USD": USD, "JPY": JPY}[cur])


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    c = client_mod.CnbCacheClient("http://cnb.test/cnb-cache", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_client", c)


async def call(name, args=None):
    async with Client(server.mcp) as c:
        r = await c.call_tool(name, args or {})
        return r.data


async def test_every_tool_annotated():
    async with Client(server.mcp) as c:
        tools = await c.list_tools()
    assert {t.name for t in tools} == {"get_rate", "list_currencies", "convert_amount", "get_rate_history"}
    for t in tools:
        a = t.annotations
        assert t.title and t.title != t.name
        assert None not in (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint)
        assert not (a.read_only_hint and a.destructive_hint)
        if t.name.startswith(("get_", "list_", "search_")):
            assert a.read_only_hint is True
        for p in t.input_schema.get("properties", {}).values():
            assert p.get("description")


async def test_get_rate():
    assert (await call("get_rate", {"currency": "usd"}))["rate"] == 24.0


async def test_list_currencies_json_endpoint(monkeypatch):
    def h(request):
        assert "currencies" in request.url.params
        return httpx.Response(200, json={"currencies": ["eur", "USD"], "keep_days": 3})

    monkeypatch.setattr(server, "_client", client_mod.CnbCacheClient("http://cnb.test/", transport=httpx.MockTransport(h)))
    assert await call("list_currencies") == ["EUR", "USD"]


async def test_error_redacts_credentials(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("x")

    monkeypatch.setattr(server, "_client", client_mod.CnbCacheClient("http://user:pw@cnb.test/a?token=s", transport=httpx.MockTransport(boom)))
    with pytest.raises(Exception) as e:
        await call("get_rate", {"currency": "USD"})
    assert "pw" not in str(e.value) and "token" not in str(e.value) and "cnb.test" in str(e.value)


async def test_list_currencies():
    assert await call("list_currencies") == ["JPY", "USD"]


async def test_convert_via_czk_and_amount():
    r = await call("convert_amount", {"amount": 10, "from_currency": "USD", "to_currency": "CZK"})
    assert r["result"] == 240.0
    r = await call("convert_amount", {"amount": 100, "from_currency": "JPY", "to_currency": "USD"})
    assert r["result"] == pytest.approx(0.625)


async def test_history_skips_weekend():
    r = await call("get_rate_history", {"currency": "USD", "from_date": "2025-01-24", "to_date": "2025-01-25"})
    assert len(r["rates"]) == 1 and r["skipped_days"] == ["2025-01-25"]


async def test_invalid_input():
    with pytest.raises(Exception, match="Invalid"):
        await call("get_rate", {"currency": "U$D"})
    with pytest.raises(Exception, match="Range too long"):
        await call("get_rate_history", {"currency": "USD", "from_date": "2020-01-01", "to_date": "2025-01-01"})


async def test_unreachable_has_no_secrets(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("secret-detail")

    monkeypatch.setattr(
        server, "_client", client_mod.CnbCacheClient("http://cnb.test/", transport=httpx.MockTransport(boom))
    )
    with pytest.raises(Exception) as e:
        await call("get_rate", {"currency": "USD"})
    assert "unreachable" in str(e.value) and "secret-detail" not in str(e.value)


def test_server_json_matches_tools():
    import pathlib

    sj = json.loads((pathlib.Path(__file__).parent.parent / "server.json").read_text())
    ext = sj["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]["cz.vitexsoftware.mcp"]
    assert {t["name"] for t in ext["tools"]} == {"get_rate", "list_currencies", "convert_amount", "get_rate_history"}
    envs = {e["name"] for e in sj["packages"][0]["environmentVariables"]}
    readme = (pathlib.Path(__file__).parent.parent / "README.md").read_text()
    assert all(e in readme for e in envs)
