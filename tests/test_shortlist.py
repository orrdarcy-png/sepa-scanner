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
