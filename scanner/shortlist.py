"""Write the morning-review shortlist from the scan results.

python -m scanner.shortlist site/data.json shortlist.json [site/sepa-watchlist.txt]

The optional third path also writes a TradingView watchlist import file (Import list... in the
watchlist menu), with a section per market and status, in priority order.

Picks stocks that are Breaking out or Buy-ready in either market, best first:
breakouts before buy-ready, stocks passing the fundamentals filter first, then by score.
"""
from __future__ import annotations

import json
import sys

STATUSES = ("Breaking out", "Buy-ready")
KEEP = ("code", "symbol", "name", "industry", "status", "setup", "price", "pivot", "dist_pivot",
        "rs", "score", "stage", "base_no", "warnings", "ff")


def build(data: dict, per_market: int = 15) -> dict:
    picks = []
    for mname, m in (data.get("markets") or {}).items():
        rows = [s for s in m.get("stocks", []) if s.get("status") in STATUSES]
        rows.sort(key=lambda s: (STATUSES.index(s["status"]), not (s.get("ff") or {}).get("pass"),
                                 -(s.get("score") or 0)))
        for s in rows[:per_market]:
            p = {k: s.get(k) for k in KEEP}
            p["market"] = mname
            p["currency"] = m.get("currency")
            p["as_of"] = m.get("as_of")
            p["footprint"] = (s.get("base") or {}).get("footprint")
            p["next_earnings"] = (s.get("fund") or {}).get("next_earnings")
            picks.append(p)
    picks.sort(key=lambda s: (STATUSES.index(s["status"]), not (s.get("ff") or {}).get("pass"),
                              -(s.get("score") or 0)))
    for i, p in enumerate(picks, 1):
        p["priority"] = i
    return {"generated": data.get("generated"), "stocks": picks}


def tradingview(out: dict) -> str:
    """TradingView import text: comma-separated symbols, with ###Section headers."""
    parts = []
    for mname in sorted({s["market"] for s in out["stocks"]}, key=lambda m: (m != "ASX", m)):
        for status in STATUSES:
            rows = [s for s in out["stocks"] if s["market"] == mname and s["status"] == status]
            if rows:
                parts.append(f"###{mname} {status}")
                # ASX needs its prefix (CPU, ALL, etc. are also US tickers); BRK-B -> BRK.B
                parts += [("ASX:" if mname == "ASX" else "") + s["code"].replace("-", ".") for s in rows]
    return ",".join(parts) + "\n"


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    out = build(json.load(open(src)))
    json.dump(out, open(dst, "w"), indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w").write(tradingview(out))
    print(f"::notice title=Morning review shortlist::{len(out['stocks'])} stocks saved "
          f"({sum(1 for s in out['stocks'] if s['status'] == 'Breaking out')} breaking out)")
