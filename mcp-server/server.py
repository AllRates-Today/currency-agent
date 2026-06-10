import asyncio
import logging
import os

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

API_BASE_URL = os.getenv("ALLRATES_BASE_URL", "https://allratestoday.com/api")

mcp = FastMCP("AllRatesToday Currency MCP Server 💵")


def _auth_headers() -> dict[str, str]:
    api_key = os.getenv("ALLRATES_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ALLRATES_API_KEY is not set. Sign up free at "
            "https://allratestoday.com/register to get a key."
        )
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


@mcp.tool()
def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
):
    """Use this to get the current exchange rate between two currencies.

    Args:
        currency_from: The currency to convert from (e.g., "USD").
        currency_to: The currency to convert to (e.g., "EUR").

    Returns:
        A dictionary containing the exchange rate data, or an error message if the request fails.
    """
    logger.info(
        f"--- 🛠️ Tool: get_exchange_rate called for converting {currency_from} to {currency_to} ---"
    )
    try:
        response = httpx.get(
            f"{API_BASE_URL}/rate",
            params={"source": currency_from.upper(), "target": currency_to.upper()},
            headers=_auth_headers(),
        )
        response.raise_for_status()

        data = response.json()
        if "rate" not in data:
            logger.error(f"❌ rate not found in response: {data}")
            return {"error": "Invalid API response format."}
        logger.info(f"✅ API response: {data}")
        return data
    except httpx.HTTPError as e:
        logger.error(f"❌ API request failed: {e}")
        return {"error": f"API request failed: {e}"}
    except ValueError:
        logger.error("❌ Invalid JSON response from API")
        return {"error": "Invalid JSON response from API."}


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
        f"--- 🛠️ Tool: get_historical_rates called for {currency_from}/{currency_to} over {period} ---"
    )
    if period not in ("1d", "7d", "30d", "1y"):
        return {"error": "Invalid period. Use one of: 1d, 7d, 30d, 1y."}
    try:
        response = httpx.get(
            f"{API_BASE_URL}/historical-rates",
            params={
                "source": currency_from.upper(),
                "target": currency_to.upper(),
                "period": period,
            },
            headers=_auth_headers(),
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"✅ API response received for {period} history")
        return data
    except httpx.HTTPError as e:
        logger.error(f"❌ API request failed: {e}")
        return {"error": f"API request failed: {e}"}
    except ValueError:
        logger.error("❌ Invalid JSON response from API")
        return {"error": "Invalid JSON response from API."}


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
    try:
        response = httpx.get(
            f"{API_BASE_URL}/v1/symbols",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"✅ {data.get('count', '?')} currencies returned")
        return data
    except httpx.HTTPError as e:
        logger.error(f"❌ API request failed: {e}")
        return {"error": f"API request failed: {e}"}
    except ValueError:
        logger.error("❌ Invalid JSON response from API")
        return {"error": "Invalid JSON response from API."}


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
