# SEPA Scanner

A daily stock scanner built from Mark Minervini's two books, *Trade Like a Stock Market Wizard* (2013) and *Think & Trade Like a Champion* (2017). It scans every liquid ASX stock and the US S&P 1500, finds the ones in a confirmed Stage 2 uptrend, measures their bases and volatility contraction patterns (VCPs), checks the fundamentals Yahoo has, and builds one web page you can open on your phone, tablet or computer.

The page shows:

- **Market condition**: index trend, breadth, new highs versus new lows, and the leading industry groups, with the book's guidance on how much exposure to carry.
- **Watchlist**: every stock that passes all 8 Trend Template rules, ranked and labelled *Breaking out*, *Buy-ready*, *Setting up*, *Trend only* or *Extended*, with its VCP footprint (for example `8W 22/2 3T`).
- **Stock sheet** (tap any stock): candlestick chart with the 50/150/200-day lines, base and pivot; the Trend Template checklist; the contractions; fundamentals; warnings (late-stage base, climax run, earnings coming up); a position-size calculator using the book's risk rules; and the 18 fundamental-check prompts with the stock's details already filled in.

It is a screening tool, not advice. Look at every chart yourself before you trade.

---

## Option A: put it online, updated automatically (recommended)

GitHub runs the scan for free twice every weekday and publishes the page at a web address you can open anywhere. About 10 minutes, once.

1. **Make a free GitHub account** at github.com if you don't have one.
2. **Create a repository**: click **+** (top right) → **New repository**. Name it `sepa-scanner`, choose **Public**, tick **Add a README**, click **Create repository**.
   (GitHub's free plan only publishes pages from public repositories. The page holds market data only, nothing personal.)
3. **Upload the files**: in the new repository click **Add file → Upload files**, then drag in everything inside this folder, *including the hidden `.github` folder*. On a Mac, press **Cmd + Shift + .** in Finder to show hidden folders. Click **Commit changes**.
   If the `.github` folder won't upload, add it by hand: **Add file → Create new file**, type `.github/workflows/scan.yml` as the name, paste in the contents of that file from this folder, and commit.
4. **Turn on Pages**: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **Run it the first time**: **Actions** tab → **Daily SEPA scan** → **Run workflow**. It takes 10-20 minutes. When it finishes, the run shows your page address, which will be `https://YOUR-USERNAME.github.io/sepa-scanner/`.
6. **Add it to your phone's home screen**: open the address in Safari → Share → **Add to Home Screen**.

After that it runs by itself at **5:20pm Brisbane** (after the ASX close) and **7:30am Brisbane** (after the US close), Monday to Friday.

If a run fails (the Actions tab shows a red cross), click it to read the log. The most common cause is Yahoo temporarily refusing requests; the next scheduled run usually works. You can also re-run it from the same screen.

## Option B: run it on your Mac

Double-click `run_scan.command`. The first run sets up Python packages, then it scans and opens the page in your browser. (If macOS blocks it, right-click → Open.) Add `--market ASX` to scan one market only:

```bash
./run_scan.command --market ASX
```

To check the page without downloading anything: `python3 -m scanner.run --demo`.

## Settings

Everything is in `config.yaml`: which markets to scan, the liquidity filter (default: 50-day average turnover above A$1M on the ASX, US$10M in the US), the Trend Template thresholds, the VCP rules, and the default account size and risk for the position-size calculator. Edit it on GitHub (click the file → pencil icon) and the next run uses the new values.

The fundamental prompts are in `prompts/prompts.yaml`. They are market-aware: `markets.ASX` and `markets.US` set the sources and reporting conventions in each prompt's header, and each prompt's `ASX:` / `US:` text adds checks for that market (half-yearly reports, placements and Appendix 3Y on the ASX; 10-Q, Form 4 and 13F in the US). Edit the wording there and it flows into the page.

## How to use it (the book's routine)

1. **Evening**: check the market condition first. In a correction, mostly stay in cash and build the watchlist from stocks holding up best.
2. Open each **Breaking out** and **Buy-ready** stock. Confirm the chart yourself: Stage 2, contractions getting smaller left to right, volume drying up at the right side of the base.
3. Run the **Full SEPA fundamental review** prompt on the best few. Skip anything that fails on earnings.
4. **Set price alerts at the pivot** in TradingView or CommSec. The page footer links to `sepa-watchlist.txt`, a TradingView import file of the Breaking out and Buy-ready stocks, rebuilt after each scan (watchlist menu → **Import list…**). Buy as the stock trades through the pivot on volume at least 40% above average; don't chase more than about 5% above it.
5. **Before buying, write down your stop** (no more than 10% below entry; aim for 5-6% average losses) and size the position with the calculator so the stop costs no more than 1.25-2.5% of the account.
6. Once the gain is 2-3 times your risk, move the stop to breakeven. Sell into strength on climax runs and late-stage bases; sell into weakness on the largest drop on the heaviest volume since the move began.

## What each part of the code does

| File | Job |
|---|---|
| `scanner/universe.py` | Lists every ASX company (ASX directory) and the S&P 500/400/600 (Wikipedia) |
| `scanner/data.py` | Downloads two years of daily prices from Yahoo Finance |
| `scanner/technical.py` | Trend Template, stage, RS rating, base/VCP, power play, cheat, base count, sell warnings |
| `scanner/fundamentals.py` | EPS and sales growth, acceleration, margins, Code 33, ownership, next results date |
| `scanner/market.py` | Index trend, breadth, new highs/lows, leading groups, market call |
| `scanner/run.py` | Runs everything and writes `site/index.html` and `site/data.json` |
| `scanner/template.html` | The web page |
| `prompts/prompts.yaml` | The 18 fundamental-check prompts, with ASX and US versions |
| `tests/` | Pattern tests on synthetic charts: `python -m pytest -q` |

## Known limits

- Yahoo's data for small ASX companies can have gaps or bad prints, and its fundamentals for ASX stocks are thin (most report half-yearly). The prompts are the real fundamental check.
- The RS rating is ranked within each market (ASX against ASX, US against US), the way IBD's rating works, but it is calculated here rather than taken from IBD.
- Pattern detection is a filter. It finds candidates; your eyes on the chart make the decision.
