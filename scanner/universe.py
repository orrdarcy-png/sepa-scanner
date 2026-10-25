"""Build the list of tickers to scan for each market.

ASX: every listed company from the ASX's public company directory (includes
listing date and GICS industry group, which we use for "youth" and group
leadership). Falls back to universes/asx_fallback.txt if the download fails.

US: S&P 500 + S&P 400 + S&P 600 from Wikipedia (large, mid and small caps).
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

ASX_DIRECTORY_URLS = [
    "https://asx.api.markitdigital.com/asx-research/1.0/companies/directory/file"
    "?access_token=83ff96335c2d45a094df02a206a39ff4",
    "https://www.asx.com.au/asx/research/ASXListedCompanies.csv",
]

WIKI = {
    "S&P 500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "S&P 400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "S&P 600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}


def _find_col(df: pd.DataFrame, *needles: str) -> str | None:
    for c in df.columns:
        lc = str(c).lower()
        if all(n in lc for n in needles):
            return c
    return None


def asx_universe() -> pd.DataFrame:
    """Columns: symbol (yfinance form, e.g. BHP.AX), code, name, industry, listed (date or NaT)."""
    for url in ASX_DIRECTORY_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            text = r.text
            # the old CSV has two junk lines before the header
            lines = text.splitlines()
            start = next(i for i, l in enumerate(lines[:10]) if "code" in l.lower())
            df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
            code = _find_col(df, "code")
            if code is None:
                continue
            out = pd.DataFrame({
                "code": df[code].astype(str).str.strip().str.upper(),
                "name": df[_find_col(df, "name")] if _find_col(df, "name") else "",
                "industry": df[_find_col(df, "industry")] if _find_col(df, "industry") else "",
            })
            lc = _find_col(df, "listing")
            out["listed"] = pd.to_datetime(df[lc], errors="coerce", dayfirst=True) if lc else pd.NaT
            out = out[out["code"].str.fullmatch(r"[A-Z0-9]{3,6}")]
            out["symbol"] = out["code"] + ".AX"
            if len(out) > 500:
                log.info("ASX directory: %d companies from %s", len(out), url.split("?")[0])
                return out.reset_index(drop=True)
        except Exception as e:  # noqa: BLE001
            log.warning("ASX directory download failed (%s): %s", url.split("?")[0], e)
    codes = [c.strip().upper() for c in (ROOT / "universes" / "asx_fallback.txt").read_text().split() if c.strip()]
    log.warning("Using fallback ASX list (%d names)", len(codes))
    return pd.DataFrame({"code": codes, "name": "", "industry": "", "listed": pd.NaT,
                         "symbol": [c + ".AX" for c in codes]})


def us_universe() -> pd.DataFrame:
    frames = []
    for idx, url in WIKI.items():
        try:
            html = requests.get(url, headers=UA, timeout=30).text
            for t in pd.read_html(io.StringIO(html)):
                sym = _find_col(t, "symbol") or _find_col(t, "ticker")
                if sym is None or len(t) < 100:
                    continue
                name = _find_col(t, "security") or _find_col(t, "company")
                ind = _find_col(t, "sub-industry") or _find_col(t, "industry") or _find_col(t, "sector")
                frames.append(pd.DataFrame({
                    "code": t[sym].astype(str).str.strip().str.upper(),
                    "name": t[name] if name else "",
                    "industry": t[ind] if ind else "",
                    "index": idx,
                }))
                break
        except Exception as e:  # noqa: BLE001
            log.warning("Wikipedia %s failed: %s", idx, e)
    if not frames:
        f = ROOT / "universes" / "us_fallback.txt"
        codes = f.read_text().split() if f.exists() else []
        return pd.DataFrame({"code": codes, "name": "", "industry": "", "listed": pd.NaT, "symbol": codes})
    out = pd.concat(frames).drop_duplicates("code")
    out["symbol"] = out["code"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    out["listed"] = pd.NaT
    log.info("US universe: %d names", len(out))
    return out.reset_index(drop=True)


def load_universe(market: str, spec) -> pd.DataFrame:
    if isinstance(spec, list):
        sfx = ".AX" if market == "ASX" else ""
        return pd.DataFrame({"code": spec, "name": "", "industry": "", "listed": pd.NaT,
                             "symbol": [s if s.endswith(sfx) else s + sfx for s in spec]})
    if isinstance(spec, str) and spec != "auto":
        path = ROOT / spec
        return load_universe(market, path.read_text().split())
    return asx_universe() if market == "ASX" else us_universe()
