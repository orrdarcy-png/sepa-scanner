"""Synthetic market for testing the scanner and page without internet.
Plants textbook patterns (VCPs, breakouts, a power play, cheats, downtrends) among random stocks.
Every name is clearly fake (DEMO prefix)."""
from __future__ import annotations

import numpy as np
import pandas as pd

NAMES = ["Alpha", "Bravo", "Cobalt", "Delta", "Ember", "Falcon", "Granite", "Harbour", "Iris", "Jarrah",
         "Kestrel", "Lumen", "Meridian", "Nimbus", "Opal", "Pinnacle", "Quartz", "Riverstone", "Summit", "Tidal",
         "Umbra", "Vertex", "Wattle", "Xenon", "Yarra", "Zephyr"]
INDUSTRIES = ["Software & Services", "Materials", "Health Care Equipment", "Capital Goods", "Energy",
              "Consumer Services", "Pharmaceuticals & Biotech", "Banks", "Retailing", "Media"]


def _path(segments, start, rng):
    """segments: list of (days, total_return, daily_vol, vol_level)."""
    px, vols = [start], []
    for days, ret, sig, vlev in segments:
        mu = np.log(1 + ret) / days
        for _ in range(days):
            px.append(px[-1] * float(np.exp(mu + rng.normal(0, sig))))
            vols.append(vlev * float(rng.lognormal(0, 0.35)))
    return np.array(px[1:]), np.array(vols)


def _ohlc(c, rng, sig):
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, sig / 3, len(c)))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, sig / 2, len(c))))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, sig / 2, len(c))))
    return o, h, lo


def _vcp(rng, breakout=False):
    up = [(120, 0.25, 0.012, 1.0), (90, 0.55, 0.014, 1.6)]
    base = [(12, -0.24, 0.010, 1.4), (14, 0.22, 0.010, 1.0), (10, -0.13, 0.008, 0.9),
            (10, 0.12, 0.007, 0.8), (7, -0.07, 0.006, 0.6), (7, 0.065, 0.005, 0.55), (6, -0.025, 0.003, 0.35)]
    seg = [(240, 0.05, 0.015, 1.0)] + up + base
    if breakout:
        seg += [(1, 0.06, 0.002, 2.8)]
    return seg


def demo_market(name: str, index_sym: str, n: int = 260, seed: int = 7):
    rng = np.random.default_rng(seed + (0 if name == "ASX" else 1))
    days = 500
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    sfx = ".AX" if name == "ASX" else ""
    cols, data = [], {f: {} for f in ["Open", "High", "Low", "Close", "Volume"]}
    idx_c, _ = _path([(300, 0.18, 0.008, 1), (120, -0.06, 0.009, 1), (80, 0.07, 0.007, 1)], 7000, rng)
    rows = []
    for i in range(n):
        code = f"D{NAMES[i % 26][:2].upper()}{i // 26}"
        sym = code + sfx
        kind = ["vcp", "breakout", "power", "down", "random", "random", "random", "uptrend"][i % 8] if i < 80 else "random"
        if kind == "vcp":
            seg = _vcp(rng)
        elif kind == "breakout":
            seg = _vcp(rng, breakout=True)
        elif kind == "power":
            seg = [(420, 0.1, 0.014, 1.0), (30, 1.3, 0.02, 4.0), (22, -0.08, 0.008, 1.2)]
        elif kind == "down":
            seg = [(250, 0.6, 0.015, 1.0), (250, -0.55, 0.02, 1.3)]
        elif kind == "uptrend":
            seg = [(250, 0.1, 0.014, 1), (250, 0.9, 0.016, 1.4)]
        else:
            seg = [(250, rng.normal(0.05, 0.3), 0.018, 1), (250, rng.normal(0.05, 0.35), 0.018, 1)]
        total = sum(s[0] for s in seg)
        seg = [(days - total, 0.0, 0.012, 1.0)] + seg if total < days else seg
        c, v = _path(seg, float(rng.uniform(0.5, 60)), rng)
        c, v = c[-days:], v[-days:]
        o, h, lo = _ohlc(c, rng, 0.012)
        vol = v * float(rng.uniform(2e5, 5e6))
        for f, arr in zip(["Open", "High", "Low", "Close", "Volume"], [o, h, lo, c, vol]):
            data[f][sym] = arr
        rows.append({"code": code, "symbol": sym, "name": f"DEMO {NAMES[i % 26]} {i // 26 or ''}".strip(),
                     "industry": INDUSTRIES[i % len(INDUSTRIES)],
                     "listed": pd.Timestamp("2016-01-01") + pd.Timedelta(days=int(rng.integers(0, 3500)))})
    io_, ih, il = _ohlc(idx_c[-days:], rng, 0.006)
    for f, arr in zip(["Open", "High", "Low", "Close", "Volume"], [io_, ih, il, idx_c[-days:], np.full(days, 1e9)]):
        data[f][index_sym] = arr
    px = {f: pd.DataFrame(d, index=dates) for f, d in data.items()}
    return pd.DataFrame(rows), px


def demo_fundamentals(sym: str) -> dict:
    rng = np.random.default_rng(abs(hash(sym)) % 2**32)
    base_g = rng.normal(30, 25)
    eps = [{"period": p, "value": round(float(rng.uniform(0.05, 1.5)), 3), "yoy": round(float(base_g + k * rng.normal(8, 6)), 1),
            "from_loss": False} for k, p in enumerate(["Dec 2025", "Jun 2026"])]
    rev = [{"period": p, "value": 1e8, "yoy": round(float(base_g * 0.7 + k * rng.normal(5, 4)), 1), "from_loss": False}
           for k, p in enumerate(["Dec 2025", "Jun 2026"])]
    m = [{"period": p, "margin": round(float(8 + k * rng.normal(1, 1)), 1)} for k, p in enumerate(["Jun 2025", "Dec 2025", "Jun 2026"])]
    return {"symbol": sym, "name": None, "freq": "half-yearly", "eps_yoy": eps, "rev_yoy": rev, "net_margin_trend": m,
            "eps_accel": eps[-1]["yoy"] > eps[0]["yoy"], "rev_accel": rev[-1]["yoy"] > rev[0]["yoy"],
            "margin_expanding": m[-1]["margin"] > m[-2]["margin"] > m[-3]["margin"], "code33": False,
            "mcap": float(rng.uniform(2e8, 8e9)), "float": None, "inst_pct": float(rng.uniform(0.1, 0.7)),
            "pe": round(float(rng.uniform(12, 70)), 1), "next_earnings": None, "eps_annual_yoy": [], "rev_annual_yoy": [],
            "summary": "Synthetic demo company used to test the scanner."}
