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

## Numbers check (free, every scan)

Each Breaking out and Buy-ready stock gets an automatic check of the parts of the full SEPA review that
are pure data: earnings, sales, margins, cash flow against profit, estimate surprises, dilution, insider
selling, debt and cash runway, the next results date, and recent ASX announcements or SEC filings
(capital raises, halts, offerings). The result is Pass, Mixed, Fail or No data, shown on each buy card
and in a Numbers check panel in each stock's sheet.

- A stock is "to act on" when it is Grade A and the numbers check passes.
- It replaces the daily Claude review, so nothing runs on a Claude plan day to day. A Claude review from
  the last two weeks still overrides it.
- It does not judge the catalyst, the industry group or guidance. Before a real buy, ask Claude to
  "run SEPA on <code>".
- Data is from Yahoo Finance (thin for some ASX companies), the ASX announcements feed (latest 5 per
  company) and SEC EDGAR. Yahoo can't tell planned insider sales from discretionary ones.
- Settings are in `config.yaml` under `numbers_check`. Code: `scanner/checks.py`, `scanner/news.py`.
4. **Set price alerts at the pivot** in TradingView or CommSec. The page footer links to `sepa-watchlist.txt`, a TradingView import file of the Breaking out and Buy-ready stocks, rebuilt after each scan (watchlist menu → **Import list…**). Buy as the stock trades through the pivot on volume at least 40% above average; don't chase more than about 5% above it.
5. **Before buying, write down your stop** (no more than 10% below entry; aim for 5-6% average losses) and size the position with the calculator so the stop costs no more than 1.25-2.5% of the account.
6. Once the gain is 2-3 times your risk, move the stop to breakeven. Sell into strength on climax runs and late-stage bases; sell into weakness on the largest drop on the heaviest volume since the move began.

## Trade journal

Tap **Journal** at the top of the page. Log a buy from any stock's trade plan (**Log this trade in the journal**) or with **Add a trade**. ASX and US trades are kept apart: the **ASX / US** switch at the top of the Journal shows each market's own positions, results and closed trades (US figures in US$ with the A$ result alongside), with a one-line summary of the other market underneath. Then:

- **Open positions** show profit in % and A$, R multiple (profit in units of the risk you planned), stop distance and days held, priced from the last scan. The scan saves the close of every stock it checks, so holdings that drop off the watchlist still get a price.
- **Alerts** on each position: closed at or below your stop; up 2R or more with the stop still under entry (move it to breakeven); a heavy-volume close below the 50-day; the scanner's own warnings (climax run, late-stage base, earnings due); dropped out of the Trend Template; going nowhere after 3 weeks.
- **Sell** (partial or full, with the reason), **Move stop** (keeps a history) and **Edit**.
- **Results** (per market): batting average, average gain and loss, win/loss and adjusted win/loss ratios, average R, days held for winners vs losers, a breakdown by status at entry, and coaching notes from Minervini's rules.
- **CommSec fees** are filled in automatically when you log a buy or sale, and every profit, %, R and result figure is after fees (open positions include the estimated cost to sell today). ASX, online and settled to a CDIA: A$5 up to A$1,000, A$10 to A$3,000, A$19.95 to A$10,000, A$29.95 to A$25,000, then 0.12%. US: US$5 or 0.12%, whichever is greater, plus CommSec's 0.55% currency fee on each conversion (every US buy and sale). You can overwrite the fee on any trade (for example during a $0-brokerage offer); the US rates and currency fee can be changed in the Journal's **Settings**. The trade plan on each stock also shows the round-trip fees for the suggested position.

**Where trades are stored.** This repo is public, so trades are never saved here. They live in `journal.json` in a separate **private** repo (`sepa-journal`) and are written through the GitHub API with a fine-grained token that can only touch that repo. The Journal's **Settings** walks you through making both; paste the token once on each device. Until you connect, trades are saved in that browser only. Each device keeps a copy and the two are merged on every sync, so it also works offline. Settings has a backup download and restore.

## What each part of the code does

| File | Job |
|---|---|
| `scanner/universe.py` | Lists every ASX company (ASX directory) and the S&P 500/400/600 (Wikipedia) |
| `scanner/data.py` | Downloads two years of daily prices from Yahoo Finance |
| `scanner/technical.py` | Trend Template, stage, RS rating, base/VCP, power play, cheat, base count, sell warnings |
| `scanner/fundamentals.py` | EPS and sales growth, acceleration, margins, Code 33, ownership, next results date |
| `scanner/market.py` | Index trend, breadth, new highs/lows, leading groups, market call |
| `scanner/run.py` | Runs everything and writes `site/index.html` and `site/data.json`, including the latest close of every scanned stock for the journal |
| `scanner/template.html` | The web page, including the trade journal |
| `prompts/prompts.yaml` | The 18 fundamental-check prompts, with ASX and US versions |
| `tests/` | Pattern tests on synthetic charts: `python -m pytest -q` |

## Known limits

- Yahoo's data for small ASX companies can have gaps or bad prints, and its fundamentals for ASX stocks are thin (most report half-yearly). The prompts are the real fundamental check.
- The RS rating is ranked within each market (ASX against ASX, US against US), the way IBD's rating works, but it is calculated here rather than taken from IBD.
- Pattern detection is a filter. It finds candidates; your eyes on the chart make the decision.
