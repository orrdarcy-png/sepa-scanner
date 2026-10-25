"""Market health: index trend, breadth, new highs vs new lows, and leading industry groups.

Book rules used: the best stocks lead the market at turns; watch the 52-week-high list;
in a correction look for stocks holding up (RS line at new highs); expand exposure
only as leaders break out and work; 90%+ of superperformers emerge from corrections."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .technical import sma


def index_state(ic: np.ndarray) -> dict:
    s50, s200 = sma(ic, 50), sma(ic, 200)
    t = len(ic) - 1
    hi = np.max(ic[-252:])
    return {
        "last": round(float(ic[t]), 2),
        "chg1d": round(float(ic[t] / ic[t - 1] - 1) * 100, 2),
        "above50": bool(ic[t] > s50[t]), "above200": bool(ic[t] > s200[t]),
        "ma200_rising": bool(s200[t] > s200[t - 21]),
        "ma50_rising": bool(s50[t] > s50[t - 10]),
        "from_high": round(float(ic[t] / hi - 1) * 100, 1),
        "series": [round(float(x), 1) for x in ic[-130:]],
        "m50": [None if np.isnan(x) else round(float(x), 1) for x in s50[-130:]],
        "m200": [None if np.isnan(x) else round(float(x), 1) for x in s200[-130:]],
    }


def breadth(close: pd.DataFrame) -> dict:
    c = close.ffill()
    m50 = c.rolling(50, min_periods=50).mean()
    m200 = c.rolling(200, min_periods=200).mean()
    hi = c.rolling(252, min_periods=120).max()
    lo = c.rolling(252, min_periods=120).min()
    valid = c.notna()
    pct50 = ((c > m50) & m50.notna()).sum(axis=1) / m50.notna().sum(axis=1).replace(0, np.nan) * 100
    pct200 = ((c > m200) & m200.notna()).sum(axis=1) / m200.notna().sum(axis=1).replace(0, np.nan) * 100
    nh = ((c >= hi) & valid).sum(axis=1)
    nl = ((c <= lo) & valid).sum(axis=1)
    k = 60
    return {
        "pct_above_50": round(float(pct50.iloc[-1]), 1),
        "pct_above_200": round(float(pct200.iloc[-1]), 1),
        "new_highs": int(nh.iloc[-1]), "new_lows": int(nl.iloc[-1]),
        "new_highs_5d": int(nh.iloc[-5:].sum()), "new_lows_5d": int(nl.iloc[-5:].sum()),
        "hist_pct50": [None if np.isnan(x) else round(float(x), 1) for x in pct50.iloc[-k:]],
        "hist_nh": [int(x) for x in nh.iloc[-k:]], "hist_nl": [int(x) for x in nl.iloc[-k:]],
        "dates": [d.strftime("%d %b") for d in c.index[-k:]],
    }


def regime(ix: dict, br: dict, n_tt: int, n_breakouts: int, n_total: int) -> dict:
    """Plain-language market call with the book's exposure guidance."""
    pts = 0
    pts += 1 if ix["above50"] else -1
    pts += 1 if ix["above200"] else -1
    pts += 1 if ix["ma200_rising"] else -1
    pts += 1 if br["new_highs_5d"] > br["new_lows_5d"] else -1
    pts += 1 if br["pct_above_50"] >= 50 else -1
    if pts >= 3:
        label, tone = "Uptrend", "good"
        advice = ("Leaders are breaking out. Trade normal size, add exposure only as your first buys "
                  "show profits (pilot buy, then build). Buy in order of breakout.")
    elif pts >= 0:
        label, tone = "Under pressure", "warn"
        advice = ("Mixed signals. Trade smaller, tighten stops (5-6% instead of 7-8%), take profits sooner "
                  "and insist on the very best setups.")
    else:
        label, tone = "Correction", "bad"
        advice = ("Mostly cash. Do your homework: build the watchlist from stocks holding up best and with "
                  "RS lines at new highs. The next leaders usually break out first as the market turns.")
    return {"label": label, "tone": tone, "score": pts, "advice": advice,
            "tt_count": n_tt, "breakouts": n_breakouts, "universe": n_total}


def groups(rows: list[dict], min_names: int = 2) -> list[dict]:
    df = pd.DataFrame([{"g": r.get("industry") or "Unknown", "rs": r["rs"], "tt": r["tt"]["pass"],
                        "nh": r["tt"]["pct_below_high"] <= 1} for r in rows])
    if df.empty:
        return []
    g = df[df["tt"]].groupby("g").agg(n=("rs", "size"), rs=("rs", "mean"), nh=("nh", "sum"))
    g = g[g["n"] >= min_names].sort_values(["n", "rs"], ascending=False).head(12)
    return [{"group": k, "count": int(v.n), "avg_rs": round(float(v.rs)), "new_highs": int(v.nh)}
            for k, v in g.iterrows() if k != "Unknown"]
