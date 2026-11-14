"""The numbers check: the parts of the full SEPA review (prompts/sepa_review.md) that can be worked out
from data alone, run free on every scan for each Breaking out and Buy-ready stock.

It covers earnings, sales, margins, earnings quality, surprises, supply and ownership (dilution and
insider selling), balance sheet, event risk and recent announcements or filings. It cannot judge the
catalyst, the industry group or guidance: those still need a person or a Claude review.

Each check is PASS, CAUTION, FAIL or n/a, and the verdict is:
  Pass     earnings and sales pass and nothing fails
  Mixed    something is a caution that matters, or insiders are selling
  Fail     earnings or sales fail, or a quality or balance-sheet red flag
  No data  Yahoo has no earnings or sales figures for the stock
"""
from __future__ import annotations

import datetime as dt

DEFAULTS = {
    "min_eps_growth_pct": 25, "min_sales_growth_pct": 20,
    "min_cash_conversion": 0.8,     # operating cash flow / net profit below this is a caution
    "max_dilution_pct_per_year": 5,  # share count growing faster than this is a caution
    "insider_days": 180, "insider_cluster_days": 90, "insider_cluster_sellers": 3,
    "insider_fail_pct_of_mcap": 0.25,  # clustered or repeated insider sales fail only above this share of the company
    "min_runway_months": 12, "earnings_warn_days": 14, "news_days": 30,
}

NEEDS_JUDGEMENT = ["Catalyst: what has changed that could drive earnings much higher",
                   "Category and group: leader or laggard, and whether its industry is strong",
                   "Guidance and analyst revisions since the last report"]


def _p(x, d=0):
    t = f"{x:+.{d}f}%"
    return t.replace("-0%", "0%").replace("+0%", "0%") if d == 0 else t


def _money(x, cur=""):
    if x is None:
        return "n/a"
    a = abs(x)
    s = f"{a / 1e9:.2f}B" if a >= 1e9 else f"{a / 1e6:.0f}M" if a >= 1e6 else f"{a / 1e3:.0f}k"
    return ("-" if x < 0 else "") + cur + s


def _row(check, result, finding):
    return {"check": check, "result": result, "finding": finding[:200]}


def _fresh(s: list[dict], as_of: str | None, max_days: int) -> list[dict]:
    """Drop a series whose latest period is too old to mean anything (Yahoo sometimes stops updating a row)."""
    if not s or not as_of:
        return s
    try:
        last = dt.datetime.strptime(s[-1]["period"], "%b %Y").date()
    except (ValueError, KeyError):
        return s
    return s if (dt.date.fromisoformat(as_of) - last).days <= max_days else []


def _growth_series(f: dict, key: str, annual_key: str, as_of: str | None = None):
    """Interim (quarterly or half-yearly) growth series, or the annual one when Yahoo has no interims."""
    s = _fresh(f.get(key) or [], as_of, 300)
    if s:
        return s, f.get("freq") or "interim"
    s = _fresh(f.get(annual_key) or [], as_of, 500)
    return (s, "annual") if s else ([], None)


def check_earnings(f: dict, cfg: dict, as_of: str | None = None):
    need = cfg["min_eps_growth_pct"]
    s, freq = _growth_series(f, "eps_yoy", "eps_annual_yoy", as_of)
    if not s:
        g = f.get("eps_q_growth")
        if g is None:
            return _row("Earnings", "n/a", "No EPS history from Yahoo")
        g *= 100
        return _row("Earnings", "CAUTION" if g >= 0 else "FAIL",
                    f"Latest earnings {_p(g)} on a year earlier (Yahoo summary only, no history to confirm)")
    last, prev = s[-1], (s[-2] if len(s) > 1 else None)
    trail = ", ".join(f"{x['period']} {'from a loss' if x.get('from_loss') else _p(x['yoy'])}" for x in s[-4:])
    txt = f"EPS vs a year earlier ({freq}): {trail}"
    if last["value"] <= 0:
        return _row("Earnings", "FAIL", f"Latest EPS is a loss ({last['value']}). {txt}")
    if last.get("from_loss"):
        return _row("Earnings", "PASS", f"Turned to profit from a loss. {txt}")
    if last["yoy"] < 0:
        return _row("Earnings", "FAIL", f"EPS is falling. {txt}")
    if last["yoy"] < need:
        return _row("Earnings", "CAUTION", f"Growth under {need}%. {txt}")
    # the book wants the latest two quarters or halves at 25%+; with annual figures only, the latest year
    if freq != "annual" and prev and not prev.get("from_loss") and prev["yoy"] < need:
        return _row("Earnings", "CAUTION", f"Only the latest period is {need}%+. {txt}")
    if prev and not prev.get("from_loss") and last["yoy"] < prev["yoy"] * 0.5 and last["yoy"] < need * 2:
        return _row("Earnings", "CAUTION", f"Growth has more than halved. {txt}")
    note = "Accelerating. " if prev and last["yoy"] > prev["yoy"] else "" if prev else "One period only. "
    if freq == "annual":
        note += "Annual figures only, so check the latest half. "
    return _row("Earnings", "PASS", note + txt)


def check_sales(f: dict, cfg: dict, as_of: str | None = None):
    need = cfg["min_sales_growth_pct"]
    s, freq = _growth_series(f, "rev_yoy", "rev_annual_yoy", as_of)
    if not s:
        g = f.get("rev_growth")
        if g is None:
            return _row("Sales", "n/a", "No sales history from Yahoo")
        g *= 100
        return _row("Sales", "PASS" if g >= need else "CAUTION" if g > 0 else "FAIL",
                    f"Sales {_p(g)} on a year earlier (Yahoo summary only)")
    last, prev = s[-1], (s[-2] if len(s) > 1 else None)
    txt = f"Sales vs a year earlier ({freq}): " + ", ".join(f"{x['period']} {_p(x['yoy'])}" for x in s[-4:])
    if last["yoy"] <= 0:
        return _row("Sales", "FAIL", f"Sales flat or falling. {txt}")
    if last["yoy"] < need:
        return _row("Sales", "CAUTION", f"Growth under {need}%. {txt}")
    if prev and last["yoy"] < prev["yoy"] - 10:
        return _row("Sales", "CAUTION", f"Growth is slowing. {txt}")
    return _row("Sales", "PASS", txt)


def check_margins(f: dict, deep: dict | None = None):
    nm = f.get("net_margin_trend") or []
    if len(nm) < 2:
        nm = (deep or {}).get("net_margin_annual") or nm
    if f.get("code33"):
        return _row("Margins and Code 33", "PASS", "Code 33: EPS, sales and margins all accelerating for three periods")
    if len(nm) < 2:
        return _row("Margins and Code 33", "n/a", "No margin history from Yahoo")
    last = nm[-1]
    # compare with the same period a year earlier when there is one (seasonal businesses), else the prior period
    yr = next((x for x in reversed(nm[:-1]) if x["period"][:3] == last["period"][:3]), None)
    base = yr or nm[-2]
    d = last["margin"] - base["margin"]
    txt = f"Net margin {last['margin']}% in {last['period']} vs {base['margin']}% in {base['period']}"
    if last["margin"] < 0 and d <= 0:
        return _row("Margins and Code 33", "FAIL", f"Loss-making and not improving. {txt}")
    if d > 0.5:
        return _row("Margins and Code 33", "PASS", f"Expanding. {txt}")
    if d < -1.0:
        return _row("Margins and Code 33", "FAIL" if d < -3 else "CAUTION", f"Being squeezed. {txt}")
    return _row("Margins and Code 33", "CAUTION", f"Flat. {txt}")


def check_quality(deep: dict, cfg: dict, cur=""):
    ocf, ni, per = deep.get("ocf"), deep.get("ni"), deep.get("fy") or "latest year"
    if ocf is None or ni is None:
        return _row("Earnings quality", "n/a", "No cash flow statement from Yahoo")
    bits, res = [f"{per}: operating cash flow {_money(ocf, cur)} vs net profit {_money(ni, cur)}"], "PASS"
    if ni > 0 and ocf < 0:
        res = "FAIL"
        bits.insert(0, "Reports a profit but burns cash")
    elif ni > 0 and ocf < ni * cfg["min_cash_conversion"]:
        res = "CAUTION"
        bits.insert(0, "Cash flow lags profit")
    sg = deep.get("sales_g")
    for key, name in (("recv_g", "Receivables"), ("inv_g", "Inventory")):
        g = deep.get(key)
        if g is not None and sg is not None and g > 15 and g > sg * 1.5 + 5:
            res = "CAUTION" if res == "PASS" else res
            bits.append(f"{name} {_p(g)} vs sales {_p(sg)}")
    return _row("Earnings quality", res, ". ".join(bits))


def check_surprise(f: dict):
    s = f.get("surprises") or []
    if not s:
        return _row("Surprises", "n/a", "No estimate history from Yahoo (guidance and revisions need a person)")
    txt = "Last reports vs estimates: " + ", ".join(_p(x) for x in s[-4:])
    if s[-1] < -5:
        return _row("Surprises", "FAIL" if s[-1] < -15 else "CAUTION", f"Missed estimates last report. {txt}")
    return _row("Surprises", "PASS", ("Roughly in line last report. " if s[-1] < 0 else "") + txt)


def check_supply(f: dict, deep: dict, cfg: dict, cur=""):
    bits, res = [], "PASS"
    dil = deep.get("dilution_pct_per_year")
    if dil is not None:
        bits.append(f"Share count {_p(dil, 1)} a year over {deep.get('dilution_years')} yr")
        if dil > cfg["max_dilution_pct_per_year"]:
            res = "FAIL" if dil > cfg["max_dilution_pct_per_year"] * 3 else "CAUTION"
            bits[-1] += " (heavy dilution)" if res == "FAIL" else " (dilution)"
    inst = f.get("inst_pct")
    if inst is not None:
        bits.append(f"institutions hold {min(inst, 1) * 100:.0f}%")
        if inst > 0.8 or inst < 0.2:
            res = "CAUTION" if res == "PASS" else res
            bits[-1] += " (over-owned)" if inst > 0.8 else " (little sponsorship)"
    ins = deep.get("insiders")
    if ins:
        days = ins.get("days", cfg["insider_days"])
        if ins["sellers"]:
            bits.append(f"{ins['sellers']} insider{'s' if ins['sellers'] != 1 else ''} sold {_money(ins['sale_value'], cur)} "
                        f"in {days} days (latest {ins.get('latest_sale')})")
            # clustered or repeated selling fails only when it is big next to the company (routine
            # executive sales at large companies are tiny against the market cap)
            mcap = f.get("mcap")
            share = ins["sale_value"] / mcap * 100 if mcap else None
            big = share is not None and share >= cfg["insider_fail_pct_of_mcap"]
            if share is not None:
                bits[-1] += f", {share:.2f}% of the company"
            if ins.get("cluster"):
                bits[-1] += f"; {ins['cluster']} sold within {cfg['insider_cluster_days']} days of each other"
            elif ins.get("repeat"):
                bits[-1] += f"; repeated sales by {ins['repeat']}"
            if (ins.get("cluster") or ins.get("repeat")) and big:
                res = "FAIL"
            elif ins["sale_value"] > (ins.get("buy_value") or 0) and res == "PASS":
                res = "CAUTION"
        if ins["buyers"]:
            bits.append(f"{ins['buyers']} bought on market ({_money(ins['buy_value'], cur)})")
        if not ins["sellers"] and not ins["buyers"]:
            bits.append(f"no insider buying or selling in {days} days")
    if not bits:
        return _row("Supply and ownership", "n/a", "No share count, ownership or insider data from Yahoo")
    return _row("Supply and ownership", res, (lambda t: t[:1].upper() + t[1:])("; ".join(bits)))


def check_balance(f: dict, deep: dict, cfg: dict, cur=""):
    cash = deep.get("cash", f.get("cash"))
    debt = deep.get("debt", f.get("debt"))
    ocf = deep.get("ocf")
    if cash is None and debt is None:
        return _row("Balance sheet", "n/a", "No balance sheet from Yahoo")
    net = (cash or 0) - (debt or 0)
    bits = [f"Cash {_money(cash, cur)}, debt {_money(debt, cur)}: " + ("net cash " if net >= 0 else "net debt ") + _money(abs(net), cur)]
    res = "PASS"
    if ocf is not None and ocf < 0:
        months = (cash or 0) / (-ocf / 12)
        bits.append(f"burning {_money(-ocf, cur)} a year, about {months:.0f} months of cash")
        res = "FAIL" if months < cfg["min_runway_months"] else "CAUTION"
        if res == "FAIL":
            bits.append("a capital raise looks likely")
    elif ocf is not None and net < 0 and ocf > 0 and -net > ocf * 5:
        res = "CAUTION"
        bits.append(f"net debt is {(-net / ocf):.1f}x a year's operating cash flow")
    if f.get("roe") is not None:
        bits.append(f"ROE {f['roe'] * 100:.0f}%")
    return _row("Balance sheet", res, "; ".join(bits))


def check_event(f: dict, as_of: str, cfg: dict):
    ne = f.get("next_earnings")
    if not ne:
        return _row("Event risk", "n/a", "No next results date from Yahoo")
    days = (dt.date.fromisoformat(ne) - dt.date.fromisoformat(as_of)).days
    if 0 <= days <= cfg["earnings_warn_days"]:
        return _row("Event risk", "CAUTION", f"Reports in {days} days ({ne}): wait, or go small until there's a profit cushion")
    if days < 0:
        return _row("Event risk", "PASS", f"Last reported {ne}; next date not set yet")
    return _row("Event risk", "PASS", f"Next results {ne}, {days} days away")


def check_news(news: dict | None, market: str):
    label = "Announcements" if market == "ASX" else "Filings"
    if not news or not news.get("ok"):
        return _row(label, "n/a", "Couldn't load recent " + ("ASX announcements" if market == "ASX" else "SEC filings"))
    flags = news.get("flags") or []
    if not flags:
        return _row(label, "PASS", f"No capital raise, halt or offering in the last {news.get('days', 30)} days"
                    + (f" ({news['count']} checked)" if news.get("count") else ""))
    worst = "FAIL" if any(x["level"] == "FAIL" for x in flags) else "CAUTION"
    return _row(label, worst, "; ".join(f"{x['text']} ({x['date']})" for x in flags[:3]))


def run_checks(f: dict | None, deep: dict | None, news: dict | None, market: str, as_of: str,
               cur: str = "", cfg: dict | None = None) -> dict:
    cfg = {**DEFAULTS, **(cfg or {})}
    f, deep = f or {}, deep or {}
    e, s = check_earnings(f, cfg, as_of), check_sales(f, cfg, as_of)
    rows = [e, s, check_margins(f, deep), check_quality(deep, cfg, cur), check_surprise(f),
            check_supply(f, deep, cfg, cur), check_balance(f, deep, cfg, cur), check_event(f, as_of, cfg),
            check_news(news, market)]
    by = {r["check"]: r["result"] for r in rows}
    fails = [r["check"] for r in rows if r["result"] == "FAIL"]
    cautions = [r["check"] for r in rows if r["result"] == "CAUTION"]
    hard = {"Earnings", "Sales", "Earnings quality", "Balance sheet", "Margins and Code 33"}
    if e["result"] == "n/a" and s["result"] == "n/a":
        verdict, why = "No data", "Yahoo has no earnings or sales figures: check the announcements yourself"
    elif any(c in hard for c in fails):
        verdict, why = "Fail", "Fails on " + ", ".join(c.lower() for c in fails if c in hard)
    elif fails:
        verdict, why = "Mixed", "Fails on " + ", ".join(c.lower() for c in fails)
    elif by["Earnings"] != "PASS" or by["Sales"] != "PASS":
        weak = [c.lower() for c in ("Earnings", "Sales") if by[c] != "PASS"]
        verdict, why = "Mixed", " and ".join(weak).capitalize() + (" aren't" if len(weak) > 1 else " isn't") + " strong enough yet"
    elif len([c for c in cautions if c != "Event risk"]) >= 3:
        verdict, why = "Mixed", "Earnings and sales pass, but cautions on " + ", ".join(c.lower() for c in cautions)
    else:
        verdict = "Pass"
        why = "Earnings and sales pass and nothing fails" + (
            ". Cautions: " + ", ".join(c.lower() for c in cautions) if cautions else "")
    return {"verdict": verdict, "why": why, "rows": rows, "fails": len(fails), "cautions": len(cautions)}
