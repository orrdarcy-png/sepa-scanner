"""Daily price data from Yahoo Finance (via yfinance), downloaded in chunks with retries."""
from __future__ import annotations

import logging
import time

import pandas as pd

log = logging.getLogger(__name__)
FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def download_prices(symbols: list[str], period: str = "2y", chunk: int = 150,
                    retries: int = 3, pause: float = 2.0) -> dict[str, pd.DataFrame]:
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
