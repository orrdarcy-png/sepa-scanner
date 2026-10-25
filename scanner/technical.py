"""Technical rules from SEPA: Trend Template, stage analysis, RS rating, bases/VCP,
power plays, cup-completion cheats, base counting and late-stage sell warnings.

All functions work on plain numpy arrays for one stock (oldest -> newest)."""
from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------- helpers
def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x.astype(float), 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def atr_pct(h, l, c, n=20) -> float:
    if len(c) < n + 1:
        return float(np.nanmean((h - l) / c))
    pc = c[:-1]
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - pc), abs(l[1:] - pc)))
    return float(np.mean(tr[-n:] / c[-n:]))


def rs_raw(close: pd.DataFrame) -> pd.Series:
    """IBD-style weighted 12-month performance: 40% last quarter, 20% each earlier quarter.
    Young stocks use whatever history they have."""
    c = close.ffill()
    last = c.iloc[-1]

    def ret(n):
        if len(c) <= n:
            return pd.Series(np.nan, index=c.columns)
        return last / c.iloc[-1 - n] - 1

    r63, r126, r189, r252 = ret(63), ret(126), ret(189), ret(252)
    score = 0.4 * r63 + 0.2 * r126.fillna(r63) + 0.2 * r189.fillna(r126).fillna(r63) \
        + 0.2 * r252.fillna(r189).fillna(r126).fillna(r63)
    return score


def rs_rating(raw: pd.Series) -> pd.Series:
    """Percentile rank 1-99 within the market universe."""
    r = raw.rank(pct=True)
    return (r * 98 + 1).round().clip(1, 99)


# ----------------------------------------------------------------------------- trend template
def trend_template(c, sma50, sma150, sma200, rs, cfg) -> dict:
    t = len(c) - 1
    price = c[t]
    look = min(252, len(c))
    lo52, hi52 = np.nanmin(c[-look:]), np.nanmax(c[-look:])
    up_days = cfg.get("ma200_up_days", 21)
    have200 = not np.isnan(sma200[t])
    have150 = not np.isnan(sma150[t])

    def rising_months():
        if not have200:
            return 0
        m = 0
        for k in range(0, 12):
            a, b = t - 21 * k, t - 21 * (k + 1)
            if b < 0 or np.isnan(sma200[b]) or not sma200[a] > sma200[b]:
                break
            m += 1
        return m

    months = rising_months()
    crit = {
        "above_150_200": bool(have150 and have200 and price > sma150[t] and price > sma200[t]),
        "ma150_above_200": bool(have150 and have200 and sma150[t] > sma200[t]),
        "ma200_rising": bool(have200 and t - up_days >= 0 and not np.isnan(sma200[t - up_days])
                             and sma200[t] > sma200[t - up_days]),
        "ma50_above_150_200": bool(have150 and have200 and sma50[t] > sma150[t] and sma50[t] > sma200[t]),
        "above_50": bool(not np.isnan(sma50[t]) and price > sma50[t]),
        "above_52w_low": bool(price >= lo52 * (1 + cfg["min_above_52w_low_pct"] / 100)),
        "near_52w_high": bool(price >= hi52 * (1 - cfg["max_below_52w_high_pct"] / 100)),
        "rs_70": bool(rs >= cfg["min_rs_rating"]),
    }
    young = not have200
    if young and len(c) >= 60:
        # IPO with < 200 days of trading: the 150/200-day rules can't apply yet (book: "assuming 200 days exist")
        for k in ("above_150_200", "ma150_above_200", "ma200_rising", "ma50_above_150_200"):
            crit[k] = None
    passed = sum(1 for v in crit.values() if v)
    applicable = sum(1 for v in crit.values() if v is not None)
    return {
        "criteria": crit,
        "passed": passed,
        "applicable": applicable,
        "pass": passed == applicable and applicable >= 4,
        "ma200_months_up": months,
        "pct_above_low": round((price / lo52 - 1) * 100, 1),
        "pct_below_high": round((1 - price / hi52) * 100, 1),
        "young": young,
    }


def stage(c, sma50, sma200, tt) -> str:
    t = len(c) - 1
    if tt["pass"]:
        return "2"
    if np.isnan(sma200[t]):
        return "2?" if c[t] > sma50[t] else "1"
    slope = sma200[t] / sma200[max(0, t - 21)] - 1 if not np.isnan(sma200[max(0, t - 21)]) else 0
    if c[t] < sma200[t] and slope < -0.005 and sma50[t] < sma200[t]:
        return "4"
    hi_idx = int(np.nanargmax(c[-min(252, len(c)):]))
    days_since_high = min(252, len(c)) - 1 - hi_idx
    if abs(slope) <= 0.01 and days_since_high < 130 and tt["pct_below_high"] > 10:
        return "3"
    if c[t] > sma200[t] and slope > 0 and sma50[t] > sma200[t]:
        return "2-"  # uptrend but not every trend-template box ticked
    return "1"


# ----------------------------------------------------------------------------- swings / VCP
def zigzag(h, l, th):
    """Swing points starting from a swing high at index 0. Returns (swings, state, cur_ext_idx)."""
    swings = [("H", 0, h[0])]
    state, ext_i, ext_p = "down", 0, l[0]
    ext_i, ext_p = 0, l[0]
    for i in range(1, len(h)):
        if state == "down":
            if l[i] < ext_p:
                ext_i, ext_p = i, l[i]
            if h[i] >= ext_p * (1 + th) and ext_i < i:
                swings.append(("L", ext_i, ext_p))
                state, ext_i, ext_p = "up", i, h[i]
        else:
            if h[i] > ext_p:
                ext_i, ext_p = i, h[i]
            if l[i] <= ext_p * (1 - th) and ext_i < i:
                swings.append(("H", ext_i, ext_p))
                state, ext_i, ext_p = "down", i, l[i]
    return swings, state, ext_i, ext_p


def find_base(o, h, l, c, v, end: int, cfg: dict, index_c=None) -> dict | None:
    """Analyse the consolidation that ends at bar `end` (inclusive)."""
    min_days, max_days = cfg["min_base_days"], cfg["max_base_days"]
    lo = max(0, end - max_days)
    s = lo + int(np.argmax(h[lo:end + 1]))
    length = end - s
    if length < min_days:
        return None
    H, L, C, V = h[s:end + 1], l[s:end + 1], c[s:end + 1], v[s:end + 1]
    base_high = H[0]
    base_low = float(np.min(L))
    depth = (base_high - base_low) / base_high * 100
    th = float(np.clip(2.5 * atr_pct(h[:end + 1], l[:end + 1], c[:end + 1]), 0.04, 0.12))
    swings, state, ext_i, ext_p = zigzag(H, L, th)

    contractions = []
    for k in range(len(swings) - 1):
        if swings[k][0] == "H" and swings[k + 1][0] == "L":
            hp, lp = swings[k][2], swings[k + 1][2]
            contractions.append({"hi_i": s + swings[k][1], "lo_i": s + swings[k + 1][1],
                                 "depth": round((hp - lp) / hp * 100, 1)})
    if state == "down":
        # right side still pulling back from the last swing high
        hp = swings[-1][2] if swings[-1][0] == "H" else base_high
        hi_i = swings[-1][1] if swings[-1][0] == "H" else 0
        contractions.append({"hi_i": s + hi_i, "lo_i": s + ext_i, "depth": round((hp - ext_p) / hp * 100, 1),
                             "open": True})
        pivot = hp
        pivot_i = s + hi_i
    else:
        # rallying off the last low: the latest high is the pivot; any dip since is the final (tightest) T
        pivot, pivot_i = ext_p, s + ext_i
        after = L[ext_i + 1:]
        if len(after) >= 2:
            d = (ext_p - float(np.min(after))) / ext_p * 100
            contractions.append({"hi_i": pivot_i, "lo_i": s + ext_i + 1 + int(np.argmin(after)),
                                 "depth": round(d, 1), "open": True})
    # count the Ts from the deepest (left-side) correction rightward; earlier wiggles are noise
    if contractions:
        k0 = int(np.argmax([x["depth"] for x in contractions]))
        contractions = contractions[k0:]
    depths = [x["depth"] for x in contractions]
    n = len(depths)
    final = depths[-1] if depths else depth
    # tightness of the last 10 sessions and volume dry-up
    w = min(10, len(C))
    tight10 = (np.max(H[-w:]) - np.min(L[-w:])) / np.max(H[-w:]) * 100
    avg50 = float(np.mean(v[max(0, end - 49):end + 1]))
    vol10 = float(np.mean(V[-w:])) / avg50 if avg50 else np.nan
    minvol_ratio = float(np.min(V[-w:])) / avg50 if avg50 else np.nan
    dryup_low = bool(len(V) > w and np.min(V[-w:]) <= np.min(V[:-w]))
    progressive = sum(1 for i in range(1, n) if depths[i] <= depths[i - 1] * 1.1) / max(1, n - 1) if n > 1 else 0.0
    lows = [l[x["lo_i"]] for x in contractions]
    higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i - 1]) / max(1, len(lows) - 1) if len(lows) > 1 else 0
    # depth relative to the market's own correction over the same window
    mkt_ratio = None
    if index_c is not None:
        ic = index_c[s:end + 1]
        if len(ic) and np.all(np.isfinite(ic)):
            mdd = (np.max(ic) - np.min(ic[int(np.argmax(ic)):])) / np.max(ic) * 100
            mkt_ratio = round(depth / mdd, 1) if mdd > 1 else None

    valid = (2 <= n <= 6 and depth <= cfg["max_base_depth_pct"] and final <= cfg["max_final_contraction_pct"]
             and progressive >= 0.5)
    q = 0.0
    q += 20 if 2 <= n <= 6 else (8 if n == 1 else 0)
    q += 20 * progressive
    q += 15 if depth <= cfg["ideal_base_depth_pct"] else (7 if depth <= cfg["max_base_depth_pct"] else 0)
    q += 15 if final <= 6 else (8 if final <= 10 else 0)
    q += 15 * float(np.clip((1.0 - vol10) / 0.5, 0, 1)) if np.isfinite(vol10) else 0
    q += 5 if dryup_low else 0
    q += 10 * higher_lows
    if mkt_ratio is not None and mkt_ratio > 3:
        q -= 10

    weeks = max(1, round(length / 5))
    foot = f"{weeks}W {round(depth)}/{round(final)} {n}T"
    return {
        "start_i": int(s), "end_i": int(end), "days": int(length), "weeks": int(weeks),
        "high": float(base_high), "low": base_low, "depth": round(depth, 1), "final": round(final, 1),
        "contractions": depths, "count": n, "pivot": float(pivot), "pivot_i": int(pivot_i),
        "tight10": round(tight10, 1), "vol10": round(vol10, 2) if np.isfinite(vol10) else None,
        "minvol": round(minvol_ratio, 2) if np.isfinite(minvol_ratio) else None,
        "dryup_low": dryup_low, "progressive": round(progressive, 2), "higher_lows": round(higher_lows, 2),
        "mkt_ratio": mkt_ratio, "valid": bool(valid), "quality": round(max(0.0, min(100.0, q))),
        "footprint": foot,
    }


def power_play(h, l, c, v) -> dict | None:
    """High tight flag: +100% in <= 8 weeks on big volume, then a 3-6 week flag that corrects <= 20-25%."""
    t = len(c) - 1
    if t < 60:
        return None
    win = h[max(0, t - 45):t - 7]
    if len(win) == 0:
        return None
    hi_i = max(0, t - 45) + int(np.argmax(win))
    lo_i = max(0, hi_i - 40) + int(np.argmin(l[max(0, hi_i - 40):hi_i + 1]))
    gain = h[hi_i] / l[lo_i] - 1
    flag_days = t - hi_i
    corr = (h[hi_i] - np.min(l[hi_i:t + 1])) / h[hi_i]
    pre = v[max(0, lo_i - 50):lo_i]
    vol_mult = float(np.mean(v[lo_i:hi_i + 1]) / np.mean(pre)) if len(pre) > 10 and np.mean(pre) > 0 else np.nan
    if gain >= 1.0 and 8 <= flag_days <= 35 and corr <= 0.25 and (np.isnan(vol_mult) or vol_mult >= 1.5):
        return {"gain": round(gain * 100), "flag_days": int(flag_days), "correction": round(corr * 100, 1),
                "vol_mult": round(vol_mult, 1) if np.isfinite(vol_mult) else None, "pivot": float(h[hi_i]),
                "tight": bool(corr <= 0.10)}
    return None


def cheat(base: dict, h, l, c, v) -> dict | None:
    """Cup-completion cheat (3-C) / low cheat: a 5-10% pause part-way up the right side of a 15-50% cup."""
    if base is None or base["depth"] < 15 or base["depth"] > 50 or base["days"] < 15:
        return None
    t = len(c) - 1
    rec = (c[t] - base["low"]) / (base["high"] - base["low"]) if base["high"] > base["low"] else 0
    if not 0.25 <= rec <= 0.85:
        return None
    best = None
    for p in range(5, 21):
        hh, ll = np.max(h[t - p + 1:t + 1]), np.min(l[t - p + 1:t + 1])
        if (hh - ll) / hh <= 0.10:
            best = p
        else:
            break
    if best is None:
        return None
    avg50 = np.mean(v[max(0, t - 49):t + 1])
    vr = float(np.mean(v[t - best + 1:t + 1]) / avg50) if avg50 else np.nan
    if np.isfinite(vr) and vr > 1.0:
        return None
    return {"kind": "low cheat" if rec < 0.4 else "cheat (3-C)", "pause_days": best,
            "pivot": float(np.max(h[t - best + 1:t + 1])), "recovered": round(rec * 100), "vol": round(vr, 2)}


def base_count(h, l, c, sma200) -> int:
    """Rough count of Stage 2 bases since the stock last spent 10+ days under its 200-day line."""
    n = len(c)
    start = 0
    below = 0
    for i in range(n):
        if not np.isnan(sma200[i]) and c[i] < sma200[i]:
            below += 1
            if below >= 10:
                start = i
        else:
            below = 0
    count, run_max, run_i = 0, h[start], start
    for i in range(start + 1, n):
        if h[i] > run_max:
            if i - run_i >= 15 and (run_max - np.min(l[run_i:i])) / run_max >= 0.10:
                count += 1
            run_max, run_i = h[i], i
    if n - 1 - run_i >= 15 and (run_max - np.min(l[run_i:])) / run_max >= 0.10:
        count += 1  # base in progress
    return max(1, count)


def sell_warnings(o, h, l, c, v, sma50, base_no) -> list[str]:
    t = len(c) - 1
    out = []
    if t < 60:
        return out
    up10 = int(np.sum(np.diff(c[-11:]) > 0))
    g15 = c[t] / np.min(c[-16:]) - 1
    if g15 >= 0.25 and up10 >= 7:
        out.append(f"Climax-style run: +{round(g15 * 100)}% in 3 weeks, {up10} of last 10 days up")
    chg = np.diff(c) / c[:-1]
    look = min(120, len(chg))
    worst_i = len(chg) - look + int(np.argmin(chg[-look:]))
    vmax_i = len(v) - look + int(np.argmax(v[-look:]))
    if t - (worst_i + 1) <= 10 and chg[worst_i] < -0.04:
        out.append("Largest one-day drop in 6 months happened in the last 2 weeks")
    if vmax_i >= t - 10 and c[vmax_i] < c[vmax_i - 1]:
        out.append("Heaviest volume in 6 months came on a down day recently")
    avg50 = np.mean(v[-50:])
    if c[t] < sma50[t] and v[t] > 1.5 * avg50:
        out.append("Closed below the 50-day line on heavy volume")
    if not np.isnan(sma50[t]) and c[t] / sma50[t] - 1 > 0.25:
        out.append(f"Extended {round((c[t] / sma50[t] - 1) * 100)}% above the 50-day line")
    if base_no >= 4:
        out.append(f"Late-stage base (≈ base {base_no}): treat as a trade, sell into strength")
    return out


def up_down_volume(c, v, n=50) -> float | None:
    d = np.diff(c[-(n + 1):])
    vv = v[-n:]
    up, dn = vv[d > 0].sum(), vv[d < 0].sum()
    return round(float(up / dn), 2) if dn > 0 else None


# ----------------------------------------------------------------------------- one stock
def analyze(o, h, l, c, v, rs, index_c, cfg_tt, cfg_vcp) -> dict:
    s50, s150, s200 = sma(c, 50), sma(c, 150), sma(c, 200)
    tt = trend_template(c, s50, s150, s200, rs, cfg_tt)
    st = stage(c, s50, s200, tt)
    t = len(c) - 1
    avg50v = float(np.mean(v[-50:]))
    res = {"tt": tt, "stage": st, "price": float(c[t]), "chg1d": round((c[t] / c[t - 1] - 1) * 100, 2),
           "vol_ratio": round(float(v[t] / avg50v), 2) if avg50v else None,
           "updown_vol": up_down_volume(c, v), "ma": {"50": s50[t], "150": s150[t], "200": s200[t]}}

    base = find_base(o, h, l, c, v, t, cfg_vcp, index_c)
    status, pivot, setup = "Trend only", None, None
    # did it break out of a valid base in the last 1-3 sessions?
    for j in (1, 2, 3):
        if t - j < 60:
            break
        b = find_base(o, h, l, c, v, t - j, cfg_vcp, index_c)
        if b is not None and not (b["valid"] and c[t] > b["pivot"]):
            break  # an intact base as of t-j that hasn't been cleared: no recent breakout
        if b and b["valid"] and c[t] > b["pivot"]:
            bo_day = next(i for i in range(t - j + 1, t + 1) if c[i] > b["pivot"])
            vm = v[bo_day] / np.mean(v[max(0, bo_day - 50):bo_day])
            j = t - bo_day + 1
            ext = (c[t] / b["pivot"] - 1) * 100
            if ext <= cfg_vcp["max_chase_pct"]:
                status, pivot, setup = "Breaking out", b["pivot"], "VCP"
                base = b
                res["breakout"] = {"days_ago": j - 1, "vol_mult": round(float(vm), 2),
                                   "strong_volume": bool(vm >= cfg_vcp["breakout_volume_mult"]),
                                   "above_pivot_pct": round(ext, 1)}
            else:
                status, pivot, setup, base = "Extended", b["pivot"], "VCP", b
            break
    if status == "Trend only" and base:
        pivot = base["pivot"]
        below = (1 - c[t] / pivot) * 100
        if base["valid"] and 0 <= below <= cfg_vcp["buy_zone_pct"]:
            status, setup = "Buy-ready", "VCP"
        elif base["count"] >= 2 and base["depth"] <= cfg_vcp["max_base_depth_pct"] and below <= 15:
            status, setup = "Setting up", "VCP" if base["valid"] else "Base"
    pp = power_play(h, l, c, v)
    if pp:
        res["power_play"] = pp
        if status in ("Trend only", "Setting up"):
            below = (1 - c[t] / pp["pivot"]) * 100
            if -cfg_vcp["max_chase_pct"] <= below <= cfg_vcp["buy_zone_pct"]:
                status, setup, pivot = ("Buy-ready" if below >= 0 else "Breaking out"), "Power play", pp["pivot"]
    ch = cheat(base, h, l, c, v)
    if ch:
        res["cheat"] = ch
        if status in ("Trend only", "Setting up"):
            below = (1 - c[t] / ch["pivot"]) * 100
            if 0 <= below <= 4:
                status, setup, pivot = "Buy-ready", ch["kind"], ch["pivot"]
    if status == "Trend only" and not np.isnan(s50[t]) and c[t] / s50[t] - 1 > 0.20:
        status = "Extended"

    bc = base_count(h, l, c, s200)
    res.update({"status": status, "setup": setup, "pivot": pivot, "base": base, "base_no": bc,
                "dist_pivot": round((c[t] / pivot - 1) * 100, 1) if pivot else None,
                "warnings": sell_warnings(o, h, l, c, v, s50, bc)})
    # chart payload: last 130 sessions
    k = min(130, len(c))
    r = lambda a: [None if not np.isfinite(x) else (round(float(x), 3) if abs(x) < 10 else round(float(x), 2)) for x in a[-k:]]
    res["chart"] = {"o": r(o), "h": r(h), "l": r(l), "c": r(c), "v": [int(x) for x in v[-k:]],
                    "m50": r(s50), "m150": r(s150), "m200": r(s200), "offset": int(len(c) - k)}
    return res
