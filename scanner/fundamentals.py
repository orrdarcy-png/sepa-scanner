"""Fundamental overlay (SEPA element 2): EPS and sales growth, acceleration, margins,
Code 33, surprises, size/float, ownership and the next earnings date.

Yahoo's coverage is uneven, especially for ASX companies (which mostly report
half-yearly), so every field is optional and shown as "n/a" when missing. The
fundamental prompt pack is the deeper check."""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _num(x):
    try:
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:  # noqa: BLE001
        return None


def _row(df: pd.DataFrame, *names):
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def _yoy_series(s: pd.Series) -> list[dict]:
    """Year-over-year % change for each period that has a comparable period ~1 year earlier."""
    if s is None:
        return []
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    out = []
    for d, val in s.items():
        prior = s[(s.index <= d - pd.Timedelta(days=330)) & (s.index >= d - pd.Timedelta(days=400))]
        if len(prior):
            p = float(prior.iloc[-1])
            if p != 0:
                g = (float(val) - p) / abs(p) * 100
                out.append({"period": d.strftime("%b %Y"), "value": round(float(val), 4), "yoy": round(g, 1),
                            "from_loss": p < 0})
    return out


def _accelerating(yoy: list[dict], n=2) -> bool | None:
    if len(yoy) < n + 1:
        return None
    g = [x["yoy"] for x in yoy[-(n + 1):]]
    return all(g[i] > g[i - 1] for i in range(1, len(g)))


def fetch_one(symbol: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(symbol)
    out: dict = {"symbol": symbol}
    try:
        info = t.get_info() or {}
    except Exception as e:  # noqa: BLE001
        log.debug("info %s: %s", symbol, e)
        info = {}
    g = info.get
    out.update({
        "name": g("shortName") or g("longName"),
        "sector": g("sector"), "industry": g("industry"),
        "mcap": _num(g("marketCap")), "float": _num(g("floatShares")), "shares": _num(g("sharesOutstanding")),
        "inst_pct": _num(g("heldPercentInstitutions")), "insider_pct": _num(g("heldPercentInsiders")),
        "pe": _num(g("trailingPE")), "fwd_pe": _num(g("forwardPE")),
        "eps_q_growth": _num(g("earningsQuarterlyGrowth")), "rev_growth": _num(g("revenueGrowth")),
        "gross_margin": _num(g("grossMargins")), "op_margin": _num(g("operatingMargins")),
        "net_margin": _num(g("profitMargins")), "roe": _num(g("returnOnEquity")),
        "debt": _num(g("totalDebt")), "cash": _num(g("totalCash")),
        "analysts": _num(g("numberOfAnalystOpinions")), "rec": g("recommendationKey"),
        "first_trade": _num(g("firstTradeDateEpochUtc") or (g("firstTradeDateMilliseconds") or 0) / 1000 or None),
        "summary": (g("longBusinessSummary") or "")[:400],
    })
    ne = g("earningsTimestampStart") or g("earningsTimestamp")
    out["next_earnings"] = pd.to_datetime(ne, unit="s").strftime("%Y-%m-%d") if ne else None

    # quarterly / half-yearly statements
    try:
        q = t.quarterly_income_stmt
    except Exception:  # noqa: BLE001
        q = None
    try:
        a = t.income_stmt
    except Exception:  # noqa: BLE001
        a = None
    freq = None
    if q is not None and not q.empty and q.shape[1] >= 2:
        gaps = np.diff(sorted(pd.to_datetime(q.columns)))
        days = np.median([x / np.timedelta64(1, "D") for x in gaps])
        freq = "half-yearly" if days > 140 else "quarterly"
    out["freq"] = freq
    eps_q = _row(q, "Diluted EPS", "Basic EPS")
    rev_q = _row(q, "Total Revenue", "Operating Revenue")
    ni_q = _row(q, "Net Income", "Net Income Common Stockholders")
    out["eps_yoy"] = _yoy_series(eps_q)
    out["rev_yoy"] = _yoy_series(rev_q)
    if rev_q is not None and ni_q is not None:
        m = (ni_q / rev_q.replace(0, np.nan) * 100).dropna()
        m.index = pd.to_datetime(m.index)
        out["net_margin_trend"] = [{"period": d.strftime("%b %Y"), "margin": round(float(x), 1)}
                                   for d, x in m.sort_index().items()]
    # US names: reported EPS history from the earnings calendar gives more quarters + surprises
    try:
        ed = t.get_earnings_dates(limit=12)
        if ed is not None and not ed.empty and "Reported EPS" in ed.columns:
            ed = ed.dropna(subset=["Reported EPS"]).sort_index()
            rep = ed["Reported EPS"]
            rep.index = pd.to_datetime(rep.index).tz_localize(None)
            hist = _yoy_series(rep)
            if len(hist) > len(out["eps_yoy"]):
                out["eps_yoy"] = hist
            if "Surprise(%)" in ed.columns:
                out["surprises"] = [round(float(x), 1) for x in ed["Surprise(%)"].dropna().tail(4)]
    except Exception:  # noqa: BLE001
        pass
    eps_a = _row(a, "Diluted EPS", "Basic EPS")
    rev_a = _row(a, "Total Revenue", "Operating Revenue")
    out["eps_annual_yoy"] = _yoy_series(eps_a)
    out["rev_annual_yoy"] = _yoy_series(rev_a)
    if eps_a is not None:
        ea = eps_a.dropna().sort_index()
        out["eps_breakout_year"] = bool(len(ea) >= 3 and ea.iloc[-1] > ea.iloc[:-1].max())

    out["eps_accel"] = _accelerating(out["eps_yoy"])
    out["rev_accel"] = _accelerating(out["rev_yoy"])
    nm = out.get("net_margin_trend") or []
    out["margin_expanding"] = (len(nm) >= 3 and nm[-1]["margin"] > nm[-2]["margin"] > nm[-3]["margin"]) if nm else None
    # Code 33: three periods of acceleration in EPS, sales and margins together
    out["code33"] = bool(_accelerating(out["eps_yoy"], 3) and _accelerating(out["rev_yoy"], 3)
                         and len(nm) >= 4 and all(nm[-i]["margin"] > nm[-i - 1]["margin"] for i in (1, 2, 3)))
    return out


def fetch_many(symbols: list[str], workers: int = 6) -> dict[str, dict]:
    res = {}
    with ThreadPoolExecutor(workers) as ex:
        for sym, r in zip(symbols, ex.map(_safe, symbols)):
            res[sym] = r
    return res


def _safe(sym):
    try:
        return fetch_one(sym)
    except Exception as e:  # noqa: BLE001
        log.warning("fundamentals %s failed: %s", sym, e)
        return {"symbol": sym}


def fundamental_score(f: dict, cfg: dict) -> tuple[int, list[str]]:
    """0-20 points plus plain-English notes."""
    pts, notes = 0, []
    eps = f.get("eps_yoy") or []
    rev = f.get("rev_yoy") or []
    if eps:
        last = eps[-1]["yoy"]
        if last >= cfg["min_eps_growth_pct"] and not eps[-1]["from_loss"]:
            pts += 6
            notes.append(f"EPS +{last:.0f}% YoY latest period")
        elif eps[-1]["from_loss"] and eps[-1]["value"] > 0:
            pts += 4
            notes.append("EPS turned positive from a loss (turnaround)")
        elif last < 0:
            notes.append(f"EPS down {last:.0f}% YoY: fails the earnings test")
    elif f.get("eps_q_growth") is not None:
        g = f["eps_q_growth"] * 100
        if g >= cfg["min_eps_growth_pct"]:
            pts += 4
            notes.append(f"Latest quarterly earnings +{g:.0f}% (Yahoo summary)")
    if rev:
        last = rev[-1]["yoy"]
        if last >= cfg["min_sales_growth_pct"]:
            pts += 5
            notes.append(f"Sales +{last:.0f}% YoY")
        elif last < 0:
            notes.append(f"Sales falling {last:.0f}% YoY")
    elif f.get("rev_growth") is not None and f["rev_growth"] * 100 >= cfg["min_sales_growth_pct"]:
        pts += 3
        notes.append(f"Sales +{f['rev_growth'] * 100:.0f}% (Yahoo summary)")
    if f.get("eps_accel"):
        pts += 3
        notes.append("EPS growth accelerating")
    if f.get("rev_accel"):
        pts += 2
        notes.append("Sales growth accelerating")
    if f.get("margin_expanding"):
        pts += 2
        notes.append("Net margins expanding")
    if f.get("code33"):
        pts += 2
        notes.append("Code 33: EPS, sales and margins all accelerating")
    if f.get("eps_breakout_year"):
        notes.append("Annual EPS at a record (breakout year)")
    s = f.get("surprises") or []
    if s and s[-1] > 5:
        notes.append(f"Beat estimates by {s[-1]:.0f}% last report")
    if f.get("pe") is not None and f["pe"] < 6:
        notes.append(f"Very low P/E ({f['pe']:.1f}): book warns this can signal trouble")
    return min(20, pts), notes
