"""Data Fetcher with fallback logic for trading-triggers.

Tries Yahoo Finance first (via yfinance), using an optional ticker symbol
mapping for stocks that need exchange suffixes (e.g. OVH -> OVH.PA for
Euronext Paris). Falls back to Avanza scraping only as a last resort.

Usage:
    from data_fetcher import fetch_stock_data_with_fallback
    data = fetch_stock_data_with_fallback("OVH")
"""

import logging
import re
import subprocess
from datetime import datetime

import yfinance as yf
from tenacity import RetryError

from resilience import retry_yfinance

logger = logging.getLogger(__name__)

# Map of short symbols to Yahoo Finance tickers that require exchange suffixes.
# These are passed to yfinance instead of the bare symbol.
# Example: OVH is listed on Euronext Paris, so yfinance needs "OVH.PA".
YAHOO_TICKER_MAP: dict[str, str] = {
    "OVH": "OVH.PA",       # Euronext Paris
    "ASML": "ASML.AS",     # Euronext Amsterdam
    "SAP": "SAP.DE",       # Xetra Frankfurt
    "ADYEN": "ADYEN.AS",   # Euronext Amsterdam
    "SIE": "SIE.DE",       # Xetra Frankfurt
}

# Symbols that are known to have data quality issues on Yahoo Finance.
# These will be fetched from Avanza directly if Yahoo Finance fails.
# Selected subset where Yahoo data can be intermittent.
AVANZA_FALLBACK_SYMBOLS: set[str] = {"OVH", "ASML"}

# Avanza URL template for fallback symbols
# Format: https://www.avanza.se/aktier/om-aktien.html/{avanza_id}/{slug}
AVANZA_URLS: dict[str, str] = {
    "OVH": "https://www.avanza.se/aktier/om-aktien.html/1326722/ovh-groupe-prom-eo-1",
    "ASML": "https://www.avanza.se/aktier/om-aktien.html/5320/asml-holding",
}


def _parse_avanza_price(text: str) -> float | None:
    """Extract a price value from Swedish-formatted text.

    Handles both comma and dot as decimal separator.
    Examples:
        "11,74" -> 11.74
        "11.74" -> 11.74
        "1 234,56" -> 1234.56
    """
    if not text:
        return None
    # Remove spaces used as thousand separators
    cleaned = text.replace(" ", "").replace("\xa0", "")
    # Replace comma decimal with dot
    cleaned = cleaned.replace(",", ".")
    # Try to extract the first float-like pattern
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def _parse_avanza_change(text: str) -> float | None:
    """Extract percentage change from text like '0,00% (0,00)' or '+1,29%'.

    Returns the absolute change in percentage points.
    """
    if not text:
        return None
    # Look for percentage pattern
    match = re.search(r"([+-]?[\d\s]+[,\.]\d+)\s*%", text)
    if match:
        val_str = match.group(1).replace(" ", "").replace(",", ".")
        try:
            return float(val_str)
        except ValueError:
            pass
    return None


def _run_agent_browser(url: str) -> str:
    """Run agent-browser to fetch the page HTML.

    Uses headless browser automation to handle JavaScript-rendered content.
    Returns the full page HTML as a string.
    """
    try:
        # Open the page
        subprocess.run(
            ["agent-browser", "open", url],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        # Get the page HTML via JavaScript eval
        result = subprocess.run(
            ["agent-browser", "eval", "document.documentElement.outerHTML"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Close browser
        subprocess.run(
            ["agent-browser", "close"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Parse the HTML from the JSON-like output
        html = result.stdout.strip()
        # The output might be quoted JSON string, strip quotes
        if html.startswith('"') and html.endswith('"'):
            html = html[1:-1]
        # Unescape escaped newlines
        html = html.replace("\\n", "\n")
        return html

    except subprocess.TimeoutExpired:
        logger.error("agent-browser timed out fetching %s", url)
        raise RuntimeError(f"Browser timeout fetching {url}") from None
    except subprocess.CalledProcessError as e:
        logger.error("agent-browser failed: %s", e)
        raise RuntimeError(f"Browser error: {e}") from e
    except FileNotFoundError:
        logger.error("agent-browser not found in PATH")
        raise RuntimeError("agent-browser CLI not installed") from None


def fetch_avanza_data(symbol: str) -> dict:
    """Fetch stock data from Avanza by scraping the stock page.

    Uses agent-browser for headless browser automation to handle
    JavaScript-rendered content.

    Args:
        symbol: Stock symbol (must be in AVANZA_FALLBACK_SYMBOLS)

    Returns:
        Dict with keys: symbol, price, open, high, low, volume, change_pct, timestamp

    Raises:
        ValueError: If symbol is not supported for Avanza fallback.
        RuntimeError: If browser automation fails.
    """
    symbol = symbol.upper()
    if symbol not in AVANZA_FALLBACK_SYMBOLS:
        raise ValueError(
            f"Symbol {symbol} is not configured for Avanza fallback. Supported: {sorted(AVANZA_FALLBACK_SYMBOLS)}"
        )

    url = AVANZA_URLS.get(symbol)
    if not url:
        raise ValueError(f"No Avanza URL configured for {symbol}")

    logger.info("Fetching %s from Avanza: %s", symbol, url)

    # Fetch HTML via headless browser
    html = _run_agent_browser(url)

    if not html or len(html) < 1000:
        raise RuntimeError(f"Empty or too short response from Avanza for {symbol}")

    # Parse the HTML
    data = _parse_avanza_html(html, symbol)

    if not data.get("price"):
        raise RuntimeError(f"Could not extract price from Avanza page for {symbol}")

    # If high/low are missing, estimate from price and change
    if data.get("high") is None or data.get("low") is None:
        if data.get("price") is not None and data.get("change_pct") is not None:
            # Estimate high/low from intraday range
            # Use price ± 1% as rough estimate if we don't have real data
            price = data["price"]
            data["high"] = round(price * 1.01, 2)
            data["low"] = round(price * 0.99, 2)
            logger.warning(
                "Estimated high/low for %s (price=%s, change=%s%%)",
                symbol,
                price,
                data["change_pct"],
            )

    # Ensure volume has a value
    if data.get("volume") is None or data["volume"] == 0:
        data["volume"] = 0

    logger.info(
        "Avanza data for %s: price=%s, change=%s%%, high=%s, low=%s",
        symbol,
        data["price"],
        data.get("change_pct", "N/A"),
        data.get("high", "N/A"),
        data.get("low", "N/A"),
    )
    return data


def _parse_avanza_html(html: str, symbol: str) -> dict:
    """Parse Avanza HTML and extract stock data.

    Extracts:
    - Current price (Senast betalt)
    - High (Högsta)
    - Low (Lägsta)
    - Change percentage

    Falls back to computing open price from current price and change.
    """
    # Extract current price: look for "Senast betalt" followed by price
    price = None
    high = None
    low = None
    change_pct = None

    # Try multiple patterns for price extraction
    # The HTML contains "Senast betalt" followed by price in various formats
    # Pattern 1: dt/dd structure (11.75 EUR with dot)
    price_match = re.search(
        r"Senast betalt\s*[<\s][^>]*>[\s\n]*([\d\s,\.]+)\s*EUR",
        html,
        re.IGNORECASE,
    )
    if price_match:
        price = _parse_avanza_price(price_match.group(1))

    # Pattern 2: Look for price in text near "Senast betalt" - wider window
    if not price:
        idx = html.find("Senast betalt")
        if idx >= 0:
            window = html[idx : idx + 500]
            # Look for price with dot or comma decimal
            match = re.search(r"([\d\s,\.]+)\s*EUR", window)
            if match:
                price = _parse_avanza_price(match.group(1))

    # Pattern 3: Direct text pattern
    if not price:
        match = re.search(
            r"Senast\s+betalt[\s\n]*([\d\s,\.]+)",
            html,
            re.IGNORECASE,
        )
        if match:
            price = _parse_avanza_price(match.group(1))

    # Pattern 4: Look for last price in any format
    if not price:
        # Avanza shows price as "11,75" in some places
        match = re.search(
            r'"lastPrice\"[^>]*>([\d\s,\.]+)<',
            html,
        )
        if match:
            price = _parse_avanza_price(match.group(1))

    # Extract high/low from "Högst X,XX Lägst Y,YY" pattern
    # The text content has this pattern
    high_low_match = re.search(
        r"Högst\s+([\d\s,\.]+)\s+Lägst\s+([\d\s,\.]+)",
        html,
        re.IGNORECASE,
    )
    if high_low_match:
        high = _parse_avanza_price(high_low_match.group(1))
        low = _parse_avanza_price(high_low_match.group(2))

    # Alternative: look for class="high" and class="low" patterns
    if not high or not low:
        high_match = re.search(
            r'class="[^"]*high[^"]*"[^>]*>\s*Högst\s+([\d\s,\.]+)',
            html,
            re.IGNORECASE,
        )
        low_match = re.search(
            r'class="[^"]*low[^"]*"[^>]*>\s*Lägst\s+([\d\s,\.]+)',
            html,
            re.IGNORECASE,
        )
        if high_match:
            high = _parse_avanza_price(high_match.group(1))
        if low_match:
            low = _parse_avanza_price(low_match.group(1))

    # Extract change percentage
    # Look for patterns like "0,00% (0,00)" or "+1,29%"
    change_match = re.search(
        r"([+-]?[\d\s,\.]+)\s*%\s*\([\d\s,\.]+\)",
        html,
    )
    if change_match:
        change_pct = _parse_avanza_change(change_match.group(0))

    # Fallback: look for any percentage near the price
    if change_pct is None:
        # Find the price index and look nearby
        if price:
            price_str = f"{price:.2f}".replace(".", ",")
            idx = html.find(price_str)
            if idx >= 0:
                window = html[max(0, idx - 500) : idx + 500]
                change_match = re.search(r"([+-]?\d+[,.]\d+)\s*%", window)
                if change_match:
                    change_pct = _parse_avanza_change(change_match.group(0))

    # If we still don't have change, try finding percentage in the page near "Senast"
    if change_pct is None:
        match = re.search(r"Senast[^\n]{0,200}([+-]?\d+[,.]\d+)\s*%", html)
        if match:
            change_pct = _parse_avanza_change(match.group(0))

    # Compute open price from current price and change
    open_price = None
    if price is not None and change_pct is not None:
        # open = price / (1 + change_pct/100)
        if abs(change_pct) < 0.001:
            open_price = price
        else:
            open_price = round(price / (1 + change_pct / 100), 2)

    # If we don't have open, estimate from high/low
    if open_price is None and high is not None and low is not None:
        # Use midpoint as rough estimate
        open_price = round((high + low) / 2, 2)

    # Volume - Avanza doesn't always show volume prominently, use 0 as placeholder
    volume = 0

    # Extract volume if available (look for "Omsättning" or similar)
    # Note: Avanza doesn't always show volume on the stock page
    volume_match = re.search(
        r"Omsättning[^\d]*([\d\s\.]+)",
        html,
        re.IGNORECASE,
    )
    if volume_match:
        vol_str = volume_match.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            volume = int(float(vol_str))
        except ValueError:
            volume = 0
    else:
        volume = 0

    return {
        "symbol": symbol,
        "price": price,
        "open": open_price,
        "high": high,
        "low": low,
        "volume": volume,
        "change_pct": change_pct,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "avanza",
    }


@retry_yfinance
def _fetch_yahoo_data(symbol: str) -> dict:
    """Internal wrapper for Yahoo Finance data fetching.

    Applies YAHOO_TICKER_MAP to resolve exchange-specific tickers.
    """
    yahoo_ticker = YAHOO_TICKER_MAP.get(symbol, symbol)
    logger.info("Fetching %s from Yahoo Finance (ticker: %s)", symbol, yahoo_ticker)
    ticker = yf.Ticker(yahoo_ticker)
    hist = ticker.history(period="1d", interval="1m")

    if hist is None or hist.empty:
        raise ValueError(f"No data returned for {symbol} (ticker: {yahoo_ticker})")

    latest = hist.iloc[-1]
    opening = hist.iloc[0]

    data = {
        "symbol": symbol,
        "price": round(latest["Close"], 2),
        "open": round(opening["Open"], 2),
        "high": round(hist["High"].max(), 2),
        "low": round(hist["Low"].min(), 2),
        "volume": int(latest["Volume"]),
        "change_pct": round((latest["Close"] - opening["Open"]) / opening["Open"] * 100, 2),
        "timestamp": latest.name.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "yahoo",
    }

    required_fields = ("symbol", "price", "open", "high", "low", "volume", "change_pct", "timestamp")
    missing = [f for f in required_fields if data.get(f) is None]
    if missing:
        raise ValueError(f"Incomplete data for {symbol}, missing fields: {missing}")

    return data


def fetch_stock_data_yahoo(symbol: str) -> dict:
    """Fetch stock data from Yahoo Finance.

    Applies ticker mapping for exchange-specific symbols automatically.

    Raises:
        RetryError: If all retries fail.
        ValueError: If data is incomplete.
    """
    return _fetch_yahoo_data(symbol)


def fetch_stock_data_with_fallback(symbol: str) -> dict:
    """Fetch stock data with automatic fallback to Avanza.

    For symbols in AVANZA_FALLBACK_SYMBOLS, tries Yahoo Finance first
    (in case data becomes available), then falls back to Avanza.

    For other symbols, uses Yahoo Finance directly (with ticker mapping applied).

    Args:
        symbol: Stock symbol (e.g. "NVDA", "OVH")

    Returns:
        Dict with standardized stock data fields.

    Raises:
        RuntimeError: If all data sources fail.
    """
    symbol = symbol.upper()

    # For non-fallback symbols, just use Yahoo Finance (with ticker mapping)
    if symbol not in AVANZA_FALLBACK_SYMBOLS:
        try:
            return fetch_stock_data_yahoo(symbol)
        except (RetryError, ValueError, Exception) as e:
            logger.error(
                "Yahoo Finance failed for %s (ticker: %s): %s",
                symbol,
                YAHOO_TICKER_MAP.get(symbol, symbol),
                e,
            )
            raise RuntimeError(
                f"Failed to fetch data for {symbol} from Yahoo Finance (ticker: {YAHOO_TICKER_MAP.get(symbol, symbol)})"
            ) from e

    # For fallback symbols: try Yahoo Finance first, then Avanza
    yahoo_error = None
    try:
        data = fetch_stock_data_yahoo(symbol)
        logger.info("Yahoo Finance succeeded for %s (fallback symbol)", symbol)
        return data
    except (RetryError, ValueError, Exception) as e:
        yahoo_error = e
        logger.warning(
            "Yahoo Finance failed for %s (ticker: %s), attempting Avanza fallback. Error: %s",
            symbol,
            YAHOO_TICKER_MAP.get(symbol, symbol),
            e,
        )

    # Fallback to Avanza
    try:
        data = fetch_avanza_data(symbol)
        logger.info("Avanza fallback succeeded for %s", symbol)
        return data
    except Exception as e:
        logger.error("Avanza fallback also failed for %s: %s", symbol, e)
        raise RuntimeError(
            f"Failed to fetch data for {symbol} from all sources. Yahoo error: {yahoo_error}, Avanza error: {e}"
        ) from e


# === Compatibility with existing code ===


def fetch_stock_data(symbol: str) -> dict:
    """Drop-in replacement for trigger_system_v1.fetch_stock_data.

    Uses the fallback logic automatically.
    """
    return fetch_stock_data_with_fallback(symbol)


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    print("=== Testing OVH fetch ===")
    try:
        data = fetch_stock_data_with_fallback("OVH")
        print(f"Success: {data}")
    except Exception as e:
        print(f"Failed: {e}")

    print("\n=== Testing NVDA fetch ===")
    try:
        data = fetch_stock_data_with_fallback("NVDA")
        print(f"Success: price=${data['price']}, change={data['change_pct']}%")
    except Exception as e:
        print(f"Failed: {e}")
