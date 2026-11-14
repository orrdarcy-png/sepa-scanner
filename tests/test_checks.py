"""Numbers check, insider summary and announcement flags. Run: python -m pytest -q"""
import pandas as pd

from scanner.checks import run_checks
from scanner.fundamentals import insider_summary
from scanner.news import asx_summary, sec_summary

AS_OF = "2026-11-13"


def yoy(*vals, value=1.0):
    return [{"period": p, "value": value, "yoy": v, "from_loss": False}
            for p, v in zip(["Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"][-len(vals):], vals)]


def strong():
    f = {"eps_yoy": yoy(40, 60), "rev_yoy": yoy(25, 30), "freq": "quarterly", "mcap": 5e9, "inst_pct": 0.5,
         "net_margin_trend": [{"period": "Sep 2025", "margin": 8.0}, {"period": "Jun 2026", "margin": 9.0},
                              {"period": "Sep 2026", "margin": 11.0}],
         "surprises": [5.0, 12.0], "next_earnings": "2027-01-25", "roe": 0.2}
    d = {"ocf": 120e6, "ni": 100e6, "fy": "FY to Jun 2026", "sales_g": 25, "recv_g": 20, "cash": 50e6, "debt": 10e6,
         "dilution_pct_per_year": 0.5, "dilution_years": 3,
         "insiders": {"days": 180, "sellers": 0, "sales": 0, "sale_value": 0, "buyers": 0, "buys": 0, "buy_value": 0,
                      "latest_sale": None, "cluster": None, "repeat": None}}
    return f, d, {"ok": True, "days": 30, "count": 2, "flags": []}


def verdict(f, d, n, market="US"):
    return run_checks(f, d, n, market, AS_OF, "US$")


def result(c, check):
    return next(r["result"] for r in c["rows"] if r["check"] == check)


def test_strong_stock_passes():
    c = verdict(*strong())
    assert c["verdict"] == "Pass" and c["fails"] == 0
    assert all(r["result"] == "PASS" for r in c["rows"])


def test_falling_eps_fails():
    f, d, n = strong()
    f["eps_yoy"] = yoy(30, -12)
    c = verdict(f, d, n)
    assert c["verdict"] == "Fail" and result(c, "Earnings") == "FAIL"


def test_slow_sales_is_mixed():
    f, d, n = strong()
    f["rev_yoy"] = yoy(9, 12)
    c = verdict(f, d, n)
    assert c["verdict"] == "Mixed" and result(c, "Sales") == "CAUTION"


def test_only_latest_quarter_strong_is_caution_but_annual_data_passes():
    f, d, n = strong()
    f["eps_yoy"] = yoy(10, 60)
    assert result(verdict(f, d, n), "Earnings") == "CAUTION"
    f["eps_yoy"], f["eps_annual_yoy"] = [], yoy(10, 60)
    assert result(verdict(f, d, n), "Earnings") == "PASS"


def test_turnaround_from_loss_passes_earnings():
    f, d, n = strong()
    f["eps_yoy"] = [{"period": "Sep 2026", "value": 0.4, "yoy": 300.0, "from_loss": True}]
    assert result(verdict(f, d, n), "Earnings") == "PASS"


def test_profit_without_cash_fails_quality():
    f, d, n = strong()
    d["ocf"] = -20e6
    c = verdict(f, d, n)
    assert result(c, "Earnings quality") == "FAIL" and c["verdict"] == "Fail"


def test_short_cash_runway_fails_balance_sheet():
    f, d, n = strong()
    d.update(ocf=-60e6, ni=-50e6, cash=30e6)
    assert result(verdict(f, d, n), "Balance sheet") == "FAIL"


def test_insider_cluster_fails_only_when_large():
    f, d, n = strong()
    d["insiders"].update(sellers=4, sales=6, sale_value=2e6, latest_sale="2026-10-01", cluster=4)
    c = verdict(f, d, n)                      # 0.04% of a 5B company: routine
    assert result(c, "Supply and ownership") == "CAUTION" and c["verdict"] == "Pass"
    d["insiders"]["sale_value"] = 40e6        # 0.8% of the company
    c = verdict(f, d, n)
    assert result(c, "Supply and ownership") == "FAIL" and c["verdict"] == "Mixed"


def test_heavy_dilution_fails_supply_even_if_over_owned():
    f, d, n = strong()
    d["dilution_pct_per_year"], f["inst_pct"] = 40.0, 0.95
    assert result(verdict(f, d, n), "Supply and ownership") == "FAIL"


def test_earnings_soon_is_a_caution_that_does_not_block():
    f, d, n = strong()
    f["next_earnings"] = "2026-11-19"
    c = verdict(f, d, n)
    assert result(c, "Event risk") == "CAUTION" and c["verdict"] == "Pass"


def test_stale_series_is_ignored():
    f, d, n = strong()
    f["rev_yoy"] = [{"period": "Jun 2024", "value": 1.0, "yoy": 40.0, "from_loss": False}]
    assert result(verdict(f, d, n), "Sales") == "n/a"


def test_no_data():
    c = run_checks({}, {}, {"ok": False}, "ASX", AS_OF, "A$")
    assert c["verdict"] == "No data" and result(c, "Announcements") == "n/a"


def test_insider_summary_counts_sales_and_clusters():
    tx = pd.DataFrame({
        "Text": ["Sale at price 10.00 per share.", "Sale at price 10.00 per share.", "Sale at price 11.00 per share.",
                 "Stock Award(Grant) at price 0.00 per share.", "Purchase at price 9.00 per share.",
                 "Sale at price 5.00 per share."],
        "Insider": ["A", "B", "C", "A", "D", "E"],
        "Value": [100.0, 200.0, 300.0, 0.0, 50.0, 999.0],
        "Start Date": ["2026-10-01", "2026-10-20", "2026-11-02", "2026-10-05", "2026-09-01", "2025-01-01"]})
    s = insider_summary(tx, pd.Timestamp(AS_OF))
    assert (s["sellers"], s["sale_value"], s["buyers"], s["buy_value"]) == (3, 600.0, 1, 50.0)
    assert s["cluster"] == 3 and s["latest_sale"] == "2026-11-02"
    assert insider_summary(None, pd.Timestamp(AS_OF)) is None


def test_asx_announcements_flag_raises_and_halts():
    items = [{"date": "2026-11-10", "headline": "Proposed issue of securities - XYZ", "type": "ISSUED CAPITAL", "sensitive": False},
             {"date": "2026-11-09", "headline": "Trading Halt", "type": "", "sensitive": True},
             {"date": "2026-11-01", "headline": "Half Year Results", "type": "", "sensitive": True},
             {"date": "2026-08-01", "headline": "Placement completed", "type": "", "sensitive": True}]
    s = asx_summary(items, "XYZ", AS_OF)
    assert [f["text"].split(":")[0] for f in s["flags"]] == ["Capital raise or new shares", "Trading halt"]
    assert asx_summary([{"date": "2026-11-10", "headline": "Ceasing to be a substantial holder", "type": "", "sensitive": False}],
                       "XYZ", AS_OF)["flags"] == []
    assert s["count"] == 3 and s["url"].endswith("/XYZ")
    c = run_checks({}, {}, s, "ASX", AS_OF, "A$")
    assert result(c, "Announcements") == "CAUTION"


def test_sec_filings_flag_offerings_and_restatements():
    recent = {"form": ["144", "8-K", "424B5", "8-K", "10-Q", "8-K"],
              "filingDate": ["2026-11-12", "2026-11-05", "2026-11-03", "2026-10-28", "2026-10-27", "2026-05-01"],
              "items": ["", "4.02", "", "2.02,9.01", "", "2.02"]}
    s = sec_summary(recent, 123, AS_OF)
    assert [f["level"] for f in s["flags"]] == ["FAIL", "CAUTION"]
    assert s["form144_90d"] == 1 and s["count"] == 5
    assert any(x["tag"] == "results" for x in s["items"])
    assert result(run_checks({}, {}, s, "US", AS_OF, "US$"), "Filings") == "FAIL"
