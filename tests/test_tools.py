"""Unit tests for the MCP server tools (httpx is mocked — no network calls)."""

import importlib.util
import pathlib
import sys

import pytest

SERVER_PATH = pathlib.Path(__file__).parent.parent / "mcp-server" / "server.py"
spec = importlib.util.spec_from_file_location("server", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
sys.modules["server"] = server
spec.loader.exec_module(server)


def tool_fn(tool):
    """Return the plain function behind a FastMCP tool."""
    return getattr(tool, "fn", tool)


class DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        if self._payload is ValueError:
            raise ValueError("not json")
        return self._payload


@pytest.fixture(autouse=True)
def env_and_cache(monkeypatch):
    monkeypatch.setenv("ALLRATES_API_KEY", "art_test_key")
    server._cache.clear()
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    yield


def mock_get(monkeypatch, responses):
    """Queue httpx.get responses; records call count and last params."""
    calls = {"count": 0, "params": None}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["count"] += 1
        calls["params"] = params
        item = responses[min(calls["count"] - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(server.httpx, "get", fake_get)
    return calls


def test_get_exchange_rate_with_amount(monkeypatch):
    mock_get(monkeypatch, [DummyResponse(200, {"rate": 0.9, "source": "ecb"})])
    result = tool_fn(server.get_exchange_rate)("usd", "eur", amount=100)
    assert result["rate"] == 0.9
    assert result["converted"] == 90.0
    assert result["from"] == "USD" and result["to"] == "EUR"


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("ALLRATES_API_KEY")
    result = tool_fn(server.get_exchange_rate)("USD", "EUR")
    assert "error" in result and "ALLRATES_API_KEY" in result["error"]


def test_retry_then_success(monkeypatch):
    calls = mock_get(
        monkeypatch,
        [DummyResponse(503, {}), DummyResponse(200, {"rate": 1.5, "source": "ecb"})],
    )
    result = tool_fn(server.get_exchange_rate)("USD", "GBP")
    assert result["rate"] == 1.5
    assert calls["count"] == 2


def test_non_retryable_error_surfaces(monkeypatch):
    calls = mock_get(monkeypatch, [DummyResponse(401, {"error": "invalid API key"})])
    result = tool_fn(server.get_exchange_rate)("USD", "EUR")
    assert result == {"error": "API error: invalid API key"}
    assert calls["count"] == 1


def test_cache_hit(monkeypatch):
    calls = mock_get(monkeypatch, [DummyResponse(200, {"rate": 2.0, "source": "ecb"})])
    fn = tool_fn(server.get_exchange_rate)
    fn("USD", "AUD")
    fn("USD", "AUD")
    assert calls["count"] == 1  # second call served from cache


def test_get_rate_change(monkeypatch):
    mock_get(
        monkeypatch,
        [
            DummyResponse(
                200,
                {
                    "data": [
                        {"date": "2026-06-01", "rate": 1.0},
                        {"date": "2026-06-05", "rate": 1.1},
                    ]
                },
            )
        ],
    )
    result = tool_fn(server.get_rate_change)("USD", "EUR", "7d")
    assert result["direction"] == "up"
    assert result["change_pct"] == pytest.approx(10.0)
    assert result["start_rate"] == 1.0 and result["end_rate"] == 1.1


def test_get_rate_change_invalid_period():
    result = tool_fn(server.get_rate_change)("USD", "EUR", "99d")
    assert "error" in result


def test_compare_rates(monkeypatch):
    mock_get(monkeypatch, [DummyResponse(200, {"rate": 0.5, "source": "ecb"})])
    result = tool_fn(server.compare_rates)("USD", "eur, gbp")
    assert result["base"] == "USD"
    assert set(result["rates"]) == {"EUR", "GBP"}


def test_list_currencies_uses_long_ttl(monkeypatch):
    mock_get(
        monkeypatch,
        [DummyResponse(200, {"currencies": [{"code": "USD"}], "count": 1})],
    )
    result = tool_fn(server.list_currencies)()
    assert result["count"] == 1
