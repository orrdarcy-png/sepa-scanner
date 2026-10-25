"""Daily price data from Yahoo Finance (via yfinance), downloaded in chunks with retries."""
from __future__ import annotations

import logging
import time

import pandas as pd

log = logging.getLogger(__name__)
FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def download_prices(symbols: list[str], period: str = "2y", chunk: int = 100,
                    retries: int = 4, pause: float = 3.0) -> dict[str, pd.DataFrame]:
    """Return {field: DataFrame(index=date, columns=symbols)} with split/dividend-adjusted prices."""
    import yfinance as yf

    parts: dict[str, list[pd.DataFrame]] = {f: [] for f in FIELDS}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        for attempt in range(retries):
            try:
                df = yf.download(batch, period=period, interval="1d", auto_adjust=True,
                                 group_by="column", threads=True, progress=False)
                if df is None or df.empty:
                    raise RuntimeError("empty download")
                if not isinstance(df.columns, pd.MultiIndex):  # single ticker
                    df.columns = pd.MultiIndex.from_product([df.columns, batch])
                for f in FIELDS:
                    if f in df.columns.get_level_values(0):
                        parts[f].append(df[f])
                break
            except Exception as e:  # noqa: BLE001
                log.warning("batch %d-%d attempt %d failed: %s", i, i + len(batch), attempt + 1, e)
                time.sleep(pause * (attempt + 2))
        log.info("downloaded %d/%d", min(i + chunk, len(symbols)), len(symbols))
        time.sleep(pause)
    out = {}
    for f in FIELDS:
        if parts[f]:
            d = pd.concat(parts[f], axis=1)
            d = d.loc[:, ~d.columns.duplicated()]
            d.index = pd.to_datetime(d.index).tz_localize(None)
            out[f] = d.sort_index()
    return out


def download_index(symbols: list[str], period: str = "2y", retries: int = 4) -> tuple[str, pd.DataFrame]:
    """Fetch the market index on its own (with ETF fallbacks), so one bad batch can't sink a market."""
    import yfinance as yf

    last_err = None
    for sym in symbols:
        for attempt in range(retries):
            try:
                df = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
                if df is not None and len(df) > 200:
                    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                    return sym, df[FIELDS]
                last_err = f"{sym}: only {0 if df is None else len(df)} rows"
            except Exception as e:  # noqa: BLE001
                last_err = f"{sym}: {e}"
            log.warning("index %s attempt %d failed: %s", sym, attempt + 1, last_err)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not download the market index ({last_err})")


def aud_per(currency: str) -> float | None:
    """Australian dollars per one unit of `currency` (e.g. 'USD'), from Yahoo's latest daily close."""
    import yfinance as yf

    for attempt in range(3):
        try:
            df = yf.Ticker(f"AUD{currency}=X").history(period="1mo", interval="1d")
            c = df["Close"].dropna()
            if len(c) and c.iloc[-1] > 0:
                return float(1 / c.iloc[-1])
        except Exception as e:  # noqa: BLE001
            log.warning("FX AUD%s attempt %d failed: %s", currency, attempt + 1, e)
        time.sleep(3 * (attempt + 1))
    return None
