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


def scan_market(name: str, mcfg: dict, cfg: dict, demo: bool) -> dict:
    if demo:
        from .synthetic import demo_market
        uni, px = demo_market(name, mcfg["index"])
    else:
        from .data import download_prices
        uni = load_universe(name, mcfg.get("universe", "auto"))
        px = download_prices(list(uni["symbol"]) + [mcfg["index"]])
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
    meta = uni.drop_duplicates("symbol").set_index("symbol")
    rows = []
    for s in liquid:
        df = pd.DataFrame({"o": opn[s], "h": high[s], "l": low[s], "c": close[s], "v": vol[s]}).dropna()
        df = df[(df["c"] > 0) & (df["h"] >= df["l"])]
        if len(df) < 60:
            continue
        ic = pd.Series(index_c, index=cal).reindex(df.index).ffill().to_numpy()
        try:
            r = tech.analyze(*(df[k].to_numpy(dtype=float) for k in "ohlcv"), float(rs.get(s, 1)), ic,
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
        r.update({"symbol": s, "code": s.replace(".AX", ""), "rs": int(rs.get(s, 1)),
                  "name": (m.get("name") if hasattr(m, "get") else "") or "",
                  "industry": (m.get("industry") if hasattr(m, "get") else "") or "",
                  "listed": m.get("listed") if hasattr(m, "get") else None,
                  "turnover": float(turnover.get(s, 0)), "dates": [d.strftime("%Y-%m-%d") for d in df.index[-130:]]})
        r["score_tech"] = tech_score(r)
        rows.append(r)

    ix = mk.index_state(index_c)
    br = mk.breadth(close[liquid])
    cands = [r for r in rows if r["tt"]["pass"] or r.get("power_play")]
    cands.sort(key=lambda r: -r["score_tech"])

    # fundamentals for the strongest names
    fcfg = cfg["fundamentals"]
    if fcfg.get("enabled", True):
        from .fundamentals import fundamental_score
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
        r["score"] = round(r["score_tech"] + r.get("fund_pts", 0))
        lst = r.get("listed")
        ft = (r.get("fund") or {}).get("first_trade")
        when = pd.Timestamp(lst) if lst is not None and not pd.isna(lst) else (pd.Timestamp(ft, unit="s") if ft else None)
        r["years_listed"] = round((pd.Timestamp(cal[-1]) - when).days / 365.25, 1) if when is not None else None
    cands.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9), -r["score"]))
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
    markets = dict(prev)
    for name, mcfg in cfg["markets"].items():
        if not mcfg.get("enabled", True) or (a.market and name not in a.market):
            continue
        try:
            markets[name] = scan_market(name, mcfg, cfg, a.demo)
        except Exception as e:  # noqa: BLE001
            log.exception("%s scan failed: %s", name, e)
    data = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "demo": a.demo, "risk": cfg["risk"], "markets": markets}
    pj.write_text(json.dumps(data, separators=(",", ":")))
    build(data, outdir / "index.html")
    log.info("wrote %s", outdir / "index.html")


if __name__ == "__main__":
    main()
