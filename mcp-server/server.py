import asyncio
import logging
import os
import time

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

API_BASE_URL = os.getenv("ALLRATES_BASE_URL", "https://allratestoday.com/api")
REQUEST_TIMEOUT = 10.0
MAX_RETRIES = 3
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
RATE_TTL = 300  # seconds — live rates are cached briefly to save API quota
SYMBOLS_TTL = 86400  # the currency list rarely changes
VALID_PERIODS = ("1d", "7d", "30d", "1y")

mcp = FastMCP("AllRatesToday Currency MCP Server 💵")

_cache: dict[str, tuple[float, dict]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def _cache_set(key: str, value: dict, ttl: float) -> None:
    _cache[key] = (time.time() + ttl, value)


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("error"), str):
            return body["error"]
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


def api_get(path: str, params: dict | None = None, *, ttl: float = RATE_TTL) -> dict:
    """GET from the AllRatesToday API with caching, timeout, and retries.

    Returns the parsed JSON on success, or {"error": "..."} on failure.
    """
    api_key = os.getenv("ALLRATES_API_KEY")
    if not api_key:
        return {
            "error": (
                "ALLRATES_API_KEY is not set. Sign up free at "
                "https://allratestoday.com/register to get a key."
            )
        }

    params = params or {}
    cache_key = f"{path}?{sorted(params.items())}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"💾 Cache hit for {path}")
        return cached

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    last_error = "unknown error"
    for attempt in range(MAX_RETRIES):
        if attempt:
            time.sleep(0.5 * 2 ** (attempt - 1))
        try:
            response = httpx.get(
                f"{API_BASE_URL}{path}",
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as e:
            last_error = f"request failed: {e}"
            logger.warning(f"⚠️ Attempt {attempt + 1}/{MAX_RETRIES} {last_error}")
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES - 1:
            last_error = _error_detail(response)
            logger.warning(f"⚠️ Attempt {attempt + 1}/{MAX_RETRIES} got {last_error}, retrying")
            continue

        if response.status_code >= 400:
            return {"error": f"API error: {_error_detail(response)}"}

        try:
            data = response.json()
        except ValueError:
            return {"error": "Invalid JSON response from API."}
        _cache_set(cache_key, data, ttl)
        return data

    return {"error": f"API request failed after {MAX_RETRIES} attempts ({last_error})."}


@mcp.tool()
def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    amount: float | None = None,
):
    """Use this to get the current exchange rate between two currencies, and
    optionally convert an amount.

    Args:
        currency_from: The currency to convert from (e.g., "USD").
        currency_to: The currency to convert to (e.g., "EUR").
        amount: Optional amount to convert (e.g., 1000). If given, the response
            includes the converted amount — prefer this over doing the
            multiplication yourself.

    Returns:
        A dictionary with the rate (and converted amount if requested), or an
        error message if the request fails.
    """
    source, target = currency_from.upper(), currency_to.upper()
    logger.info(f"--- 🛠️ Tool: get_exchange_rate {source} → {target} (amount={amount}) ---")
    data = api_get("/rate", {"source": source, "target": target})
    if "error" in data:
        return data
    rate = data.get("rate")
    result = {"from": source, "to": target, "rate": rate, "source": data.get("source")}
    if amount is not None and isinstance(rate, (int, float)):
        result["amount"] = amount
        result["converted"] = round(amount * rate, 4)
    return result


@mcp.tool()
def compare_rates(
    currency_from: str = "USD",
    currency_to_list: str = "EUR,GBP,JPY",
):
    """Use this to compare one base currency against several target currencies
    at once.

    Args:
        currency_from: The base currency (e.g., "USD").
        currency_to_list: Comma-separated target currency codes (e.g.,
            "EUR,GBP,JPY"). Maximum 10 targets.

    Returns:
        A dictionary with { base, rates: { CODE: rate, ... } } plus per-target
        errors if any lookups fail.
    """
    source = currency_from.upper()
    targets = [t.strip().upper() for t in currency_to_list.split(",") if t.strip()][:10]
    logger.info(f"--- 🛠️ Tool: compare_rates {source} vs {targets} ---")
    rates: dict[str, float] = {}
    errors: dict[str, str] = {}
    for target in targets:
        data = api_get("/rate", {"source": source, "target": target})
        if "error" in data:
            errors[target] = data["error"]
        else:
            rates[target] = data.get("rate")
    result: dict = {"base": source, "rates": rates}
    if errors:
        result["errors"] = errors
    return result


@mcp.tool()
def get_historical_rates(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    period: str = "7d",
):
    """Use this to get historical exchange rates over a period.

    Args:
        currency_from: The currency to convert from (e.g., "USD").
        currency_to: The currency to convert to (e.g., "EUR").
        period: The lookback period: "1d", "7d", "30d", or "1y". Defaults to "7d".

    Returns:
        A dictionary with a list of { date, rate } data points, or an error message.
    """
    logger.info(
        f"--- 🛠️ Tool: get_historical_rates {currency_from}/{currency_to} over {period} ---"
    )
    if period not in VALID_PERIODS:
        return {"error": f"Invalid period. Use one of: {', '.join(VALID_PERIODS)}."}
    return api_get(
        "/historical-rates",
        {
            "source": currency_from.upper(),
            "target": currency_to.upper(),
            "period": period,
        },
    )


@mcp.tool()
def get_rate_change(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    period: str = "7d",
):
    """Use this to find out how an exchange rate has moved over a period —
    e.g. to answer "is EUR up or down against USD this week?".

    Args:
        currency_from: The currency to convert from (e.g., "USD").
        currency_to: The currency to convert to (e.g., "EUR").
        period: The lookback period: "1d", "7d", "30d", or "1y". Defaults to "7d".

    Returns:
        A dictionary with start/end rates, absolute and percent change, and
        direction ("up", "down" or "flat"), or an error message.
    """
    source, target = currency_from.upper(), currency_to.upper()
    logger.info(f"--- 🛠️ Tool: get_rate_change {source}/{target} over {period} ---")
    if period not in VALID_PERIODS:
        return {"error": f"Invalid period. Use one of: {', '.join(VALID_PERIODS)}."}
    data = api_get(
        "/historical-rates",
        {"source": source, "target": target, "period": period},
    )
    if "error" in data:
        return data
    points = data.get("data") or []
    if len(points) < 2:
        return {"error": f"Not enough data points for {source}/{target} over {period}."}
    first, last = points[0], points[-1]
    start_rate, end_rate = first.get("rate"), last.get("rate")
    if not isinstance(start_rate, (int, float)) or not isinstance(end_rate, (int, float)):
        return {"error": "Unexpected data format in historical rates."}
    change = end_rate - start_rate
    change_pct = (change / start_rate * 100) if start_rate else 0.0
    return {
        "from": source,
        "to": target,
        "period": period,
        "start_date": first.get("date"),
        "start_rate": start_rate,
        "end_date": last.get("date"),
        "end_rate": end_rate,
        "change": round(change, 6),
        "change_pct": round(change_pct, 4),
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
    }


@mcp.tool()
def list_currencies():
    """Use this to list all supported currencies (150+ ISO 4217 fiat currencies).

    Call this when you are unsure whether a currency code is supported, or when
    the user asks which currencies are available.

    Returns:
        A dictionary with { currencies: [{ code, name, symbol }, ...], count },
        or an error message.
    """
    logger.info("--- 🛠️ Tool: list_currencies called ---")
    return api_get("/v1/symbols", ttl=SYMBOLS_TTL)


if __name__ == "__main__":
    logger.info(f"🚀 MCP server started on port {os.getenv('PORT', 8080)}")
    # Could also use 'sse' transport, host="0.0.0.0" required for Cloud Run.
    asyncio.run(
        mcp.run_async(
            transport="http",
            host="0.0.0.0",
            port=os.getenv("PORT", 8080),
        )
    )
