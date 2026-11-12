"""Run the SEPA scan and build the web page.

    python -m scanner.run                 # real data (Yahoo), all enabled markets
    python -m scanner.run --market ASX    # one market
    python -m scanner.run --demo          # synthetic data, no internet (for testing the page)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import market as mk
from . import technical as tech
from .build_site import build
from .universe import load_universe

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("scanner")

STATUS_ORDER = {"Breaking out": 0, "Buy-ready": 1, "Setting up": 2, "Trend only": 3, "Extended": 4}


def clean(o):
    """Make numpy / NaN values JSON-safe."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is pd.NaT:
        return None
    if isinstance(o, (pd.Timestamp, dt.date)):
        return o.strftime("%Y-%m-%d")
    return o


def tech_score(r: dict) -> float:
    tt, b = r["tt"], r.get("base")
    s = float(np.clip((r["rs"] - 70) / 29, 0, 1)) * 25
    s += float(np.clip((25 - tt["pct_below_high"]) / 25, 0, 1)) * 10
    s += min(tt["ma200_months_up"], 5)
    if b:
        s += b["quality"] / 100 * 25
    if r.get("power_play"):
        s = max(s, 60)
    ud = r.get("updown_vol") or 1
    s += float(np.clip((ud - 1) / 1, 0, 1)) * 5
    s += {1: 5, 2: 5, 3: 3}.get(r["base_no"], 0)
    return s


def price_map(close: pd.DataFrame, vol: pd.DataFrame) -> dict:
    """Latest close for every stock with recent data, so the trade journal can price any holding,
    including ones that have dropped off the watchlist. code -> [close, 1-day %, 50-day avg, volume / 50-day avg volume]."""
    out = {}
    c = close.ffill()
    last, prev = c.iloc[-1], c.iloc[-2]
    m50 = close.iloc[-50:].mean()
    v_last = vol.iloc[-1]
    v50 = vol.iloc[-51:-1].mean()
    fresh = close.iloc[-5:].notna().any()
    for s in close.columns:
        p = last.get(s)
        if not fresh.get(s, False) or p is None or not np.isfinite(p) or p <= 0:
            continue
        def r(x, n):
            return round(float(x), n) if x is not None and np.isfinite(x) else None
        chg = (p / prev[s] - 1) * 100 if prev.get(s) and np.isfinite(prev[s]) and prev[s] > 0 else None
        vr = v_last[s] / v50[s] if np.isfinite(v_last.get(s, np.nan)) and v50.get(s) and np.isfinite(v50[s]) and v50[s] > 0 else None
        out[s.replace(".AX", "")] = [r(p, 4 if p < 2 else 3), r(chg, 2), r(m50.get(s), 4 if p < 2 else 3), r(vr, 2)]
    return out


def scan_market(name: str, mcfg: dict, cfg: dict, demo: bool) -> dict:
    if demo:
        from .synthetic import demo_market
        uni, px = demo_market(name, mcfg["index"])
    else:
        from .data import download_index, download_prices
        idx_used, idx_df = download_index([mcfg["index"]] + list(mcfg.get("index_fallbacks", [])))
        uni = load_universe(name, mcfg.get("universe", "auto"))
        if len(uni) < 50:
            raise RuntimeError(f"stock list for {name} came back with only {len(uni)} names")
        px = download_prices(list(uni["symbol"]))
        if not px:
            raise RuntimeError("Yahoo returned no price data (probably rate limiting); the next run should work")
        idx_df.index = idx_df.index.normalize()
        for f in list(px):
            d = px[f]
            d.index = d.index.normalize()
            d = d[~d.index.duplicated()].reindex(d.index.union(idx_df.index))
            d[mcfg["index"]] = idx_df[f].reindex(d.index)
            px[f] = d
        if idx_used != mcfg["index"]:
            log.warning("%s: using %s instead of %s for the index", name, idx_used, mcfg["index"])
    close, high, low, opn, vol = px["Close"], px["High"], px["Low"], px["Open"], px["Volume"]
    idx_sym = mcfg["index"]
    if idx_sym not in close.columns or close[idx_sym].dropna().empty:
        raise RuntimeError(f"no index data for {idx_sym}")
    # use the index's trading calendar
    cal = close[idx_sym].dropna().index
    close, high, low, opn, vol = (d.reindex(cal) for d in (close, high, low, opn, vol))
    index_c = close[idx_sym].ffill().to_numpy()
    stocks = [s for s in close.columns if s != idx_sym]

    # liquidity filter
    last = close[stocks].ffill().iloc[-1]
    turnover = (close[stocks] * vol[stocks]).iloc[-50:].mean()
    bars = close[stocks].notna().sum()
    fresh = close[stocks].iloc[-5:].notna().any()
    liquid = [s for s in stocks if last.get(s, 0) >= mcfg["min_price"] and turnover.get(s, 0) >= mcfg["min_turnover"]
              and bars.get(s, 0) >= 60 and fresh.get(s, False)]
    log.info("%s: %d symbols, %d liquid", name, len(stocks), len(liquid))

    rs = tech.rs_rating(tech.rs_raw(close[liquid]))
    ecfg = {"gap_min_pct": 4, "gap_vol_mult": 2.0, "gap_lookback_days": 63, "breadth_on_pct": 55,
            **(cfg.get("tested_edge") or {})}
    meta = uni.drop_duplicates("symbol").set_index("symbol")
    rows = []
    for s in liquid:
        df = pd.DataFrame({"o": opn[s], "h": high[s], "l": low[s], "c": close[s], "v": vol[s]}).dropna()
        df = df[(df["c"] > 0) & (df["h"] >= df["l"])]
        if len(df) < 60:
            continue
        ic = pd.Series(index_c, index=cal).reindex(df.index).ffill().to_numpy()
        try:
            r = tech.analyze(*(df[k].to_numpy(dtype=float) for k in "ohlcv"), float(rs.get(s, 1)) if pd.notna(rs.get(s)) else 1.0, ic,
                             cfg["trend_template"], cfg["vcp"])
        except Exception as e:  # noqa: BLE001
            log.warning("analyze %s failed: %s", s, e)
            continue
        # RS line vs index
        rsl = df["c"].to_numpy() / ic
        r["rs_line"] = {
            "new_high": bool(rsl[-1] >= np.nanmax(rsl[-252:]) * 0.995),
            "up_6w": bool(len(rsl) > 30 and rsl[-1] > rsl[-31]),
            "up_13w": bool(len(rsl) > 65 and rsl[-1] > rsl[-66]),
            "series": [round(float(x / rsl[-130:][0] * 100), 1) for x in rsl[-130:]] if len(rsl) >= 130 else None,
        }
        m = meta.loc[s] if s in meta.index else {}
        r.update({"symbol": s, "code": s.replace(".AX", ""), "rs": int(rs.get(s, 1)) if pd.notna(rs.get(s)) else 1,
                  "name": (m.get("name") if hasattr(m, "get") else "") or "",
                  "industry": (m.get("industry") if hasattr(m, "get") else "") or "",
                  "listed": m.get("listed") if hasattr(m, "get") else None,
                  "turnover": float(turnover.get(s, 0)), "dates": [d.strftime("%Y-%m-%d") for d in df.index[-130:]]})
        o_, c_, v_ = (df[k].to_numpy(dtype=float) for k in "ocv")
        r["gap"] = tech.earnings_gap(o_, c_, v_, ecfg["gap_min_pct"], ecfg["gap_vol_mult"],
                                     mcfg.get("gap_lookback_days", ecfg["gap_lookback_days"]))
        r["score_tech"] = tech_score(r)
        rows.append(r)

    ix = mk.index_state(index_c)
    br = mk.breadth(close[liquid])
    cands = [r for r in rows if r["tt"]["pass"] or r.get("power_play")]
    cands.sort(key=lambda r: -r["score_tech"])

    # fundamentals for the strongest names
    fcfg = cfg["fundamentals"]
    if fcfg.get("enabled", True):
        from .fundamentals import fundamental_flags, fundamental_score
        if demo:
            from .synthetic import demo_fundamentals
            fund = {r["symbol"]: demo_fundamentals(r["symbol"]) for r in cands}
        else:
            from .fundamentals import fetch_many
            fund = fetch_many([r["symbol"] for r in cands[:fcfg["max_names_per_market"]]])
        for r in cands:
            f = fund.get(r["symbol"])
            if f:
                pts, notes = fundamental_score(f, fcfg)
                r["fund"], r["fund_pts"], r["fund_notes"] = f, pts, notes
                r["name"] = r["name"] or f.get("name") or ""
                r["industry"] = r["industry"] or f.get("industry") or f.get("sector") or ""
                ne = f.get("next_earnings")
                if ne:
                    days = (pd.Timestamp(ne) - pd.Timestamp(cal[-1])).days
                    if 0 <= days <= 14:
                        r["warnings"].append(f"Reports earnings in {days} days ({ne}): don't hold a full position "
                                             "into the report without a profit cushion")
    for r in cands:
        r["ff"] = fundamental_flags(r.get("fund"), fcfg) if fcfg.get("enabled", True) else \
            {"data": False, "eps": False, "pass": False, "accel": False, "code33": False}
        # tested edge: strong earnings gap + EPS growth, the two stock-level filters from the backtest
        r["ff"]["gap"] = bool(r.get("gap"))
        r["ff"]["edge"] = bool(r.get("gap") and r["ff"].get("eps"))
        r["score"] = round(r["score_tech"] + r.get("fund_pts", 0))
        # plain buy instruction: the trigger (pivot) and the highest price worth paying (pivot + max chase)
        if r["status"] in ("Breaking out", "Buy-ready") and r.get("pivot"):
            r["buy"] = {"trigger": r["pivot"], "max": r["pivot"] * (1 + cfg["vcp"]["max_chase_pct"] / 100),
                        "grade": "A" if r["ff"]["edge"] else "B"}
        lst = r.get("listed")
        ft = (r.get("fund") or {}).get("first_trade")
        when = pd.Timestamp(lst) if lst is not None and not pd.isna(lst) else (pd.Timestamp(ft, unit="s") if ft else None)
        r["years_listed"] = round((pd.Timestamp(cal[-1]) - when).days / 365.25, 1) if when is not None else None
    cands.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9), not r["ff"]["edge"], -r["score"]))
    n_bo = sum(1 for r in cands if r["status"] == "Breaking out")
    out = {
        "name": name, "index": idx_sym, "currency": mcfg["currency"], "as_of": cal[-1].strftime("%Y-%m-%d"),
        "index_state": ix, "breadth": br,
        "regime": mk.regime(ix, br, len(cands), n_bo, len(liquid)),
        "groups": mk.groups(rows),
        "rs_leaders_in_weak_tape": [r["code"] for r in sorted(rows, key=lambda r: -r["rs"])
                                    if r["rs_line"]["new_high"] and ix["from_high"] < -5][:15],
        "stocks": [{k: v for k, v in r.items() if k not in ("score_tech", "listed")} for r in cands],
    }
    # the backtest only bought in a "risk-on" market; half size in neutral markets did worse than sitting out
    on = bool(ix["above200"] and br["pct_above_50"] >= ecfg["breadth_on_pct"])
    out["regime"]["risk_on"] = on
    out["regime"]["tested"] = (
        f"Tested rule: new buys {'ON' if on else 'OFF'}. Index {'above' if ix['above200'] else 'below'} its 200-day, "
        f"{br['pct_above_50']}% of stocks above their 50-day (needs {ecfg['breadth_on_pct']}%+). "
        + ("" if on else "In the backtest, sitting out beat trading half size."))
    out["px"] = price_map(close[stocks], vol[stocks])
    fxc = mcfg.get("fx")  # e.g. "USD": convert to A$ for an Australian investor
    if fxc:
        if demo:
            rate = 1.53
        else:
            from .data import aud_per
            rate = aud_per(fxc)
        if rate:
            out["fx"] = {"code": fxc, "aud_per": round(rate, 4)}
    return clean(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", action="append")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(Path(a.config).read_text())
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    prev = {}
    pj = outdir / "data.json"
    if pj.exists():
        try:
            prev = json.loads(pj.read_text()).get("markets", {})
        except Exception:  # noqa: BLE001
            prev = {}
    markets = {k: v for k, v in prev.items() if k in cfg["markets"] and cfg["markets"][k].get("enabled", True)}
    errors = {}
    for name, mcfg in cfg["markets"].items():
        if not mcfg.get("enabled", True) or (a.market and name not in a.market):
            continue
        try:
            markets[name] = scan_market(name, mcfg, cfg, a.demo)
        except Exception as e:  # noqa: BLE001
            log.exception("%s scan failed: %s", name, e)
            import traceback
            tb = traceback.extract_tb(e.__traceback__)
            where = f" (at {Path(tb[-1].filename).name}:{tb[-1].lineno})" if tb else ""
            errors[name] = f"{type(e).__name__}: {e}{where}"[:300]
    data = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "demo": a.demo, "risk": cfg["risk"], "markets": markets, "errors": errors}
    pj.write_text(json.dumps(data, separators=(",", ":")))
    if os.environ.get("GITHUB_ACTIONS"):
        # surface a one-line summary per market in the Actions run page (and its API)
        for name, m in markets.items():
            print(f"::notice title={name} scan::{len(m.get('stocks', []))} stocks on the watchlist, "
                  f"{m.get('regime', {}).get('universe', '?')} liquid, data to {m.get('as_of')}")
            st = m.get("stocks", [])
            ff = [x.get("ff") or {} for x in st]
            print(f"::notice title={name} fundamentals::{sum(1 for x in ff if x.get('data'))} of {len(st)} "
                  f"have Yahoo fundamentals, {sum(1 for x in ff if x.get('pass'))} pass EPS/sales growth, "
                  f"{sum(1 for x in ff if x.get('accel'))} accelerating, {sum(1 for x in ff if x.get('code33'))} Code 33")
            print(f"::notice title={name} tested edge::{sum(1 for x in ff if x.get('gap'))} with an earnings gap, "
                  f"{sum(1 for x in ff if x.get('edge'))} gap + EPS growth, new buys "
                  f"{'ON' if m.get('regime', {}).get('risk_on') else 'OFF'}")
        for name, e in errors.items():
            print(f"::error title={name} scan failed::{e}")
    build(data, outdir / "index.html")
    log.info("wrote %s", outdir / "index.html")


if __name__ == "__main__":
    main()
