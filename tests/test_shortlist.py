"""TradingView watchlist file built from the shortlist. Run: python -m pytest -q"""
from scanner.shortlist import tradingview


def test_tradingview_sections_and_prefixes():
    out = {"stocks": [
        {"market": "US", "status": "Buy-ready", "code": "BRK-B"},
        {"market": "ASX", "status": "Buy-ready", "code": "BSL"},
        {"market": "US", "status": "Breaking out", "code": "SM"},
        {"market": "ASX", "status": "Breaking out", "code": "CPU"},
    ]}
    assert tradingview(out) == ("###ASX Breaking out,ASX:CPU,###ASX Buy-ready,ASX:BSL,"
                                "###US Breaking out,SM,###US Buy-ready,BRK.B\n")


def test_tradingview_empty():
    assert tradingview({"stocks": []}) == "\n"


def test_tested_edge_ranks_first():
    from scanner.shortlist import build
    st = lambda code, score, **ff: {"code": code, "status": "Buy-ready", "score": score, "ff": ff}
    out = build({"markets": {"US": {"stocks": [st("AAA", 90), st("BBB", 60, edge=True), st("CCC", 80, **{"pass": True})]}}})
    assert [s["code"] for s in out["stocks"]] == ["BBB", "CCC", "AAA"]
