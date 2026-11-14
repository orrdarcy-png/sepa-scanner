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


def fundamental_flags(f: dict | None, cfg: dict) -> dict:
    """Simple pass/fail flags for the watchlist filter: has data, passes growth tests, accelerating."""
    if not f or (not f.get("eps_yoy") and not f.get("rev_yoy")
                 and f.get("eps_q_growth") is None and f.get("rev_growth") is None):
        return {"data": False, "eps": False, "pass": False, "accel": False, "code33": False}
    eps, rev = f.get("eps_yoy") or [], f.get("rev_yoy") or []
    if eps:
        eps_ok = (eps[-1]["yoy"] >= cfg["min_eps_growth_pct"] and not eps[-1]["from_loss"]) or \
                 (eps[-1]["from_loss"] and eps[-1]["value"] > 0)
    else:
        eps_ok = f.get("eps_q_growth") is not None and f["eps_q_growth"] * 100 >= cfg["min_eps_growth_pct"]
    if rev:
        rev_ok = rev[-1]["yoy"] >= cfg["min_sales_growth_pct"]
    else:
        rev_ok = f.get("rev_growth") is not None and f["rev_growth"] * 100 >= cfg["min_sales_growth_pct"]
    return {"data": True, "eps": bool(eps_ok), "pass": bool(eps_ok and rev_ok),
            "accel": bool(f.get("eps_accel") or f.get("rev_accel")), "code33": bool(f.get("code33"))}


# ---------- deeper numbers for the numbers check (Breaking out and Buy-ready stocks only) ----------

def _latest_two(df: pd.DataFrame, *names):
    """(latest, prior, latest column date) for the first matching row, newest column first."""
    r = _row(df, *names)
    if r is None:
        return None, None, None
    r = r.dropna()
    if r.empty:
        return None, None, None
    r.index = pd.to_datetime(r.index)
    r = r.sort_index(ascending=False)
    return _num(r.iloc[0]), (_num(r.iloc[1]) if len(r) > 1 else None), r.index[0]


def _g(a, b):
    return round((a - b) / abs(b) * 100, 1) if a is not None and b not in (None, 0) else None


def insider_summary(tx: pd.DataFrame | None, today: pd.Timestamp, days: int = 180, cluster_days: int = 90,
                    cluster_sellers: int = 3) -> dict | None:
    """Open-market insider sales and purchases from Yahoo's insider transactions table.
    Awards, gifts and option exercises are ignored. Yahoo can't tell planned (10b5-1) sales apart."""
    if tx is None or tx.empty or "Text" not in tx.columns or "Start Date" not in tx.columns:
        return None
    t = tx.copy()
    t["when"] = pd.to_datetime(t["Start Date"], errors="coerce")
    t = t[(t["when"] >= today - pd.Timedelta(days=days)) & (t["when"] <= today + pd.Timedelta(days=1))]
    txt = t["Text"].fillna("").str.strip().str.lower()
    sales, buys = t[txt.str.startswith("sale")], t[txt.str.startswith("purchase")]
    out = {"days": days,
           "sellers": int(sales["Insider"].nunique()), "sales": int(len(sales)),
           "sale_value": float(pd.to_numeric(sales["Value"], errors="coerce").fillna(0).sum()),
           "buyers": int(buys["Insider"].nunique()), "buys": int(len(buys)),
           "buy_value": float(pd.to_numeric(buys["Value"], errors="coerce").fillna(0).sum()),
           "latest_sale": sales["when"].max().strftime("%Y-%m-%d") if len(sales) else None,
           "cluster": None, "repeat": None}
    if len(sales):
        s = sales.sort_values("when")
        # several different insiders selling within one window
        best = 0
        for d in s["when"].unique():
            w = s[(s["when"] >= d) & (s["when"] <= d + pd.Timedelta(days=cluster_days))]
            best = max(best, w["Insider"].nunique())
        if best >= cluster_sellers:
            out["cluster"] = int(best)
        # one insider selling on three or more separate days
        per = s.groupby("Insider")["when"].nunique()
        if len(per) and per.max() >= 3:
            out["repeat"] = str(per.idxmax()).title()
    return out


def fetch_deep(symbol: str, today=None, cfg: dict | None = None) -> dict:
    """Cash flow, working capital, share count and insider trades. Every field is optional."""
    import yfinance as yf

    cfg = cfg or {}
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.today().normalize()
    t = yf.Ticker(symbol)
    out: dict = {}

    def get(attr):
        try:
            d = getattr(t, attr)
            return d if d is not None and not d.empty else None
        except Exception as e:  # noqa: BLE001
            log.debug("%s %s: %s", attr, symbol, e)
            return None

    cf, bs, inc = get("cashflow"), get("balance_sheet"), get("income_stmt")
    ocf, _, when = _latest_two(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    ni, _, _ = _latest_two(inc, "Net Income", "Net Income Common Stockholders")
    out["ocf"], out["ni"] = ocf, ni
    out["fy"] = f"FY to {when.strftime('%b %Y')}" if when is not None else None
    rev, rev0, _ = _latest_two(inc, "Total Revenue", "Operating Revenue")
    out["sales_g"] = _g(rev, rev0)
    ni_a, rev_a = _row(inc, "Net Income", "Net Income Common Stockholders"), _row(inc, "Total Revenue", "Operating Revenue")
    if ni_a is not None and rev_a is not None:
        m = (ni_a / rev_a.replace(0, np.nan) * 100).dropna()
        m.index = pd.to_datetime(m.index)
        out["net_margin_annual"] = [{"period": "FY " + d.strftime("%b %Y"), "margin": round(float(x), 1)}
                                    for d, x in m.sort_index().items()]
    a, b, _ = _latest_two(bs, "Accounts Receivable", "Receivables")
    out["recv_g"] = _g(a, b)
    a, b, _ = _latest_two(bs, "Inventory")
    out["inv_g"] = _g(a, b)
    cash, _, _ = _latest_two(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
    debt, _, _ = _latest_two(bs, "Total Debt")
    if cash is not None:
        out["cash"] = cash
    if debt is not None:
        out["debt"] = debt
    sh = _row(bs, "Ordinary Shares Number", "Share Issued")
    if sh is not None:
        sh = sh.dropna()
        sh.index = pd.to_datetime(sh.index)
        sh = sh.sort_index()
        if len(sh) >= 2 and sh.iloc[0] > 0:
            yrs = max(1.0, (sh.index[-1] - sh.index[0]).days / 365.25)
            out["dilution_pct_per_year"] = round(((float(sh.iloc[-1]) / float(sh.iloc[0])) ** (1 / yrs) - 1) * 100, 1)
            out["dilution_years"] = round(yrs)
    try:
        out["insiders"] = insider_summary(t.insider_transactions, today, cfg.get("insider_days", 180),
                                          cfg.get("insider_cluster_days", 90), cfg.get("insider_cluster_sellers", 3))
    except Exception as e:  # noqa: BLE001
        log.debug("insiders %s: %s", symbol, e)
    return out


def fetch_deep_many(symbols: list[str], today=None, cfg: dict | None = None, workers: int = 4) -> dict[str, dict]:
    def one(sym):
        try:
            return fetch_deep(sym, today, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("deep fundamentals %s failed: %s", sym, e)
            return {}
    with ThreadPoolExecutor(workers) as ex:
        return dict(zip(symbols, ex.map(one, symbols)))
