"""Recent company announcements (ASX) and filings (SEC), read free on every scan for the numbers check.

Only headlines and form types are read, to flag capital raises, trading halts, offerings and restatements
and to show what is new. Both sources are best-effort: if one can't be reached the check shows "n/a"
and the scan carries on.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

import os

# The SEC asks for a name and contact address in the User-Agent. Override with the SEC_USER_AGENT variable.
UA = {"User-Agent": os.environ.get("SEC_USER_AGENT") or "sepa-scanner orrdarcy-png@users.noreply.github.com",
      "Accept": "application/json"}
ASX_URL = "https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements"
ASX_PAGE = "https://www.asx.com.au/markets/company/{code}"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_PAGE = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40"

ASX_RAISE = re.compile(r"placement|capital raising|equity raising|entitlement offer|share purchase plan|\bspp\b|"
                       r"rights issue|proposed issue of securities|appendix 3b|prospectus|institutional offer|"
                       r"retail offer|underwrit", re.I)
ASX_HALT = re.compile(r"trading halt|suspension from (official )?quotation|voluntary suspension", re.I)
ASX_RESULTS = re.compile(r"appendix 4[cde]|appendix 5b|half[- ]year|full[- ]year|annual report|quarterly|"
                         r"\bresults\b|\bfy\d\d|\b[12]h ?fy?\d\d", re.I)
ASX_HOLDER = re.compile(r"ceasing to be a substantial holder", re.I)
SEC_OFFER = {"S-1", "S-1/A", "S-3", "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "FWP"}
SEC_RESULTS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "6-K"}
ITEMS = {"2.02": "results released", "3.02": "unregistered share sale", "4.02": "past accounts can't be relied on",
         "5.02": "director or officer change", "1.01": "material agreement", "2.01": "acquisition or disposal",
         "4.01": "auditor change", "1.03": "bankruptcy"}


def _annotate(msg: str) -> None:
    """Show a data-source problem on the GitHub Actions run page."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title=Filings::{msg[:300]}")


def _day(s) -> str:
    return str(s)[:10]


def _since(as_of: str, days: int) -> str:
    return (dt.date.fromisoformat(as_of) - dt.timedelta(days=days)).isoformat()


def asx_summary(items: list[dict], code: str, as_of: str, days: int = 30) -> dict:
    """items: [{date, headline, type, sensitive}] newest first."""
    cut, flags = _since(as_of, days), []
    recent = [x for x in items if x["date"] >= cut]
    for x in recent:
        h = x["headline"]
        if ASX_RAISE.search(h) or ASX_RAISE.search(x.get("type") or ""):
            flags.append({"level": "CAUTION", "date": x["date"], "text": f"Capital raise or new shares: {h}"})
        elif ASX_HALT.search(h):
            flags.append({"level": "CAUTION", "date": x["date"], "text": f"Trading halt: {h}"})
    return {"ok": True, "days": days, "count": len(recent), "flags": flags, "url": ASX_PAGE.format(code=code),
            "note": "Latest 5 ASX announcements" if len(items) >= 5 else None,
            "items": [{"date": x["date"], "text": x["headline"], "tag": "price-sensitive" if x.get("sensitive") else
                       ("results" if ASX_RESULTS.search(x["headline"]) else
                        "holder sold down" if ASX_HOLDER.search(x["headline"]) else None)} for x in items[:5]]}


def sec_summary(recent: dict, cik: int, as_of: str, days: int = 30) -> dict:
    """recent: the 'filings.recent' object of an EDGAR submissions file (parallel lists)."""
    forms, dates = recent.get("form") or [], recent.get("filingDate") or []
    items = recent.get("items") or [""] * len(forms)
    cut, cut90, flags, shown, n144, n = _since(as_of, days), _since(as_of, 90), [], [], 0, 0
    for form, d, it in zip(forms, dates, items):
        d = _day(d)
        if d < cut90:
            break
        if form == "144":
            n144 += 1
        if d < cut:
            continue
        n += 1
        codes = [c.strip() for c in (it or "").split(",") if c.strip()]
        if form in SEC_OFFER:
            flags.append({"level": "CAUTION", "date": d, "text": f"Offering paperwork ({form}): check whether it is new shares or debt"})
        if form.startswith("8-K"):
            if "4.02" in codes or "1.03" in codes:
                flags.append({"level": "FAIL", "date": d, "text": "8-K: " + ITEMS["4.02" if "4.02" in codes else "1.03"]})
            if "3.02" in codes:
                flags.append({"level": "CAUTION", "date": d, "text": "8-K: unregistered share sale"})
            what = ", ".join(ITEMS[c] for c in codes if c in ITEMS) or "other news"
            shown.append({"date": d, "text": f"8-K: {what}", "tag": "results" if "2.02" in codes else None})
        elif form in SEC_RESULTS:
            shown.append({"date": d, "text": f"{form} filed", "tag": "results"})
        elif form in SEC_OFFER:
            shown.append({"date": d, "text": f"{form} filed", "tag": "offering"})
    if n144:
        shown.append({"date": as_of, "text": f"{n144} Form 144 notice{'s' if n144 != 1 else ''} of planned insider sales in 90 days", "tag": None})
    return {"ok": True, "days": days, "count": n, "flags": flags, "items": shown[:6], "form144_90d": n144,
            "url": SEC_PAGE.format(cik=cik)}


def fetch_asx(codes: list[str], as_of: str, days: int = 30, workers: int = 4) -> dict[str, dict]:
    import requests

    def one(code):
        try:
            r = requests.get(ASX_URL.format(code=code), headers=UA, timeout=20)
            r.raise_for_status()
            raw = (r.json().get("data") or {}).get("items") or []
            items = [{"date": _day(x.get("date")), "headline": (x.get("headline") or "").strip(),
                      "type": x.get("announcementType"), "sensitive": bool(x.get("isPriceSensitive"))} for x in raw]
            return asx_summary(sorted(items, key=lambda x: x["date"], reverse=True), code, as_of, days)
        except Exception as e:  # noqa: BLE001
            log.warning("ASX announcements %s failed: %s", code, e)
            return {"ok": False}
    with ThreadPoolExecutor(workers) as ex:
        return dict(zip(codes, ex.map(one, codes)))


def fetch_sec(tickers: list[str], as_of: str, days: int = 30) -> dict[str, dict]:
    """One request per company, kept well under the SEC's 10 requests a second limit."""
    import requests

    out = {t: {"ok": False} for t in tickers}
    try:
        r = requests.get(SEC_TICKERS, headers=UA, timeout=30)
        r.raise_for_status()
        ciks = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in r.json().values()}
    except Exception as e:  # noqa: BLE001
        log.warning("SEC ticker list failed: %s", e)
        _annotate(f"SEC ticker list: {type(e).__name__}: {e}")
        return out
    errs = []
    for t in tickers:
        cik = ciks.get(t.upper()) or ciks.get(t.upper().replace(".", "-"))
        if not cik:
            continue
        try:
            r = requests.get(SEC_SUBS.format(cik=cik), headers=UA, timeout=30)
            r.raise_for_status()
            out[t] = sec_summary((r.json().get("filings") or {}).get("recent") or {}, cik, as_of, days)
        except Exception as e:  # noqa: BLE001
            log.warning("SEC filings %s failed: %s", t, e)
            errs.append(f"{t}: {type(e).__name__}: {e}")
        time.sleep(0.15)
    if errs:
        _annotate(f"SEC filings failed for {len(errs)} of {len(tickers)}. First: {errs[0]}")
    return out
