# Full SEPA fundamental review

The method for a full Mark Minervini SEPA fundamental review of one stock, from "Trade Like a Stock
Market Wizard" (2013) and "Think & Trade Like a Champion" (2017). The on-demand command and the morning
review both follow it. Use web search for every check. The stock has usually already passed the
technical Trend Template on the scanner, so the job is the fundamental side plus event risk.

## 1. Identify the stock and its market

- ASX stock: code like PLS or PLS.AX. US stock: ticker like NVDA. If it's ambiguous (for example a code
  that exists on both), assume ASX unless told otherwise, and say so.
- Note the company name, industry, market cap and whether it reports quarterly or half-yearly.

## 2. Sources and evidence rules

- Use primary sources first and say which you used:
  - ASX: ASX announcements (asx.com.au), half-year and full-year results (Appendix 4D/4E), quarterly
    activity and cash-flow reports (Appendix 4C/5B), investor presentations, results-call notes.
  - US: SEC filings (10-Q, 10-K, 8-K), quarterly earnings releases, investor presentations,
    earnings-call transcripts.
- Use data aggregators only to fill gaps, and say so.
- Give the period and date for every number. If you can't find something, write "not found". Never
  estimate.
- Compare each period with the same period a year earlier, not the previous period.
- ASX conventions: most financial years end 30 June, so label periods like 1H FY26 (Jul-Dec 2025).
  Amounts are A$ unless the company reports in US$ (many miners do): say which. Many ASX companies
  headline "underlying" profit or EBITDA. Use it only after checking the reconciliation to statutory
  profit.
- US conventions: fiscal quarters may not match calendar quarters, so give both (for example fiscal
  Q2 FY26, Jan-Mar 2026). Say whether each EPS figure is GAAP or adjusted.

## 3. The checks

Give each check a result of PASS, CAUTION or FAIL.

1. **Earnings.** EPS for the last 4-6 periods (quarters, or halves for most ASX stocks) with growth
   against a year earlier, and whether growth is accelerating. PASS: the latest two periods are both
   +25% or better, or there's a strong, verified turnaround from losses. CAUTION: growth is positive
   but slowing, for example from 60% down to 25%. FAIL: EPS is falling or there are no earnings.
   - Ideal is 40-100%+ in a bull market.
   - Note whether the latest year is a record ("breakout year").
   - Note consensus forecasts for the next period and year.
2. **Sales.** Revenue growth against a year earlier, organic versus acquired. PASS: 20%+ and steady or
   accelerating. CAUTION: growth relies on acquisitions, one customer or one product. FAIL: flat or
   falling.
3. **Margins and Code 33.** Gross, operating and net margin trend. Code 33 means EPS, sales and margins
   all accelerating for three periods. PASS: margins expanding with sales. CAUTION: flat. FAIL: being
   squeezed.
4. **Earnings quality.** Look for:
   - one-off gains or repeated "one-off" charges
   - operating cash flow versus profit
   - inventories and receivables growing faster than sales
   - underlying versus statutory gaps (ASX)
   - GAAP versus non-GAAP gaps, stock-based pay and buybacks flattering EPS (US)

   Name the biggest concern.
5. **Surprises, guidance and revisions.** Use the last 90 days: results versus expectations, guidance
   changes and analyst estimate revisions. Rising estimates are the fuel for a move.
6. **Catalyst.** What has changed in the last 6-12 months that could drive earnings much higher? Give
   the date and source. Examples: a new product, a contract, an offtake, a resource upgrade, regulation,
   a new CEO, a new market or index inclusion. Rate it STRONG, MODERATE or WEAK. If you can't name one,
   the result is FAIL.
7. **Category and group.** Is the company a market leader, top competitor, institutional favourite,
   turnaround, cyclical or laggard? Are other stocks in its industry group also strong and near highs?
   For cyclicals and miners, say whether the cycle is early, mid or late. Give the key commodity's price
   trend, in A$ for ASX gold and lithium names.
8. **Supply and ownership.** Market cap, free float, share count growth over 3 years, recent capital
   raises or offerings, years since listing, and institutional and insider ownership. A smaller float and
   a newer company can move further.
   - **Institutional ownership:** give the percentage of shares held by institutions, with its date, its
     trend over the last 2-4 quarters, and the number of holders if found. 20-80% is fine. Below 20% (little
     sponsorship) or above 80% (over-owned: few new buyers left, many potential sellers) is CAUTION.
     ASX: use substantial holder notices and the top-20 holders in the annual report if no percentage is
     found.
   - **Insider activity:** list insider and major-holder transactions in the last 12 months (US: Form 4
     and Form 144, 13D/13G amendments; ASX: Appendix 3Y director notices and substantial holder notices
     Form 603/604/605). Separate open-market buys from sales, option exercises and planned (10b5-1) sales.
     Open-market insider buying is a positive. Clustered selling (several insiders within about 3 months)
     or repeated block sales by a director or major holder is FAIL.
9. **Balance sheet.** Cash, debt and net debt, operating cash flow and ROE. If the company is burning
   cash, give its months of runway (ASX: Appendix 4C/5B item 8.7) and the likelihood of a capital raise
   in the next 6 months. FAIL if a dilutive raise looks likely.
10. **Event risk.** List the next results date and any binary events in the next 3 months, such as drill
    results, trials, regulatory decisions or court cases. Note the short interest trend (ASX: ASIC short
    reports). Run a pre-mortem: assume the stock falls 30% in 3 months and give the three most likely
    reasons. Answer "Safe to hold through the next event?" with YES, ONLY WITH A PROFIT CUSHION or NO.
11. **Market extras.**
    - ASX: any placement, SPP or entitlement offer, or trading halt, in the last 12 months. If the
      company is an explorer or developer with no real revenue, say it can only qualify as a power play
      or story stock, not on earnings.
    - US: date of the last 10-Q and the next earnings date, and any secondary offering, shelf
      registration or at-the-market program.

## 4. Verdict

- **SEPA candidate:** earnings and sales PASS (or a verified turnaround), a catalyst you can name, no
  FAIL on quality, balance sheet or supply and ownership, and no likely raise.
- **Watch only:** the story is promising, but earnings or sales aren't there yet, or there's one
  CAUTION that matters. A FAIL on supply and ownership (insider or major-holder selling) caps the verdict
  at Watch only, even when everything else qualifies.
- **Reject:** earnings or sales FAIL, a quality red flag, a likely dilutive raise, or no catalyst.

Also give a confidence of high, medium or low, depending on how complete the data was (ASX half-yearly
data is often thin).

## 5. Output for a person (chat)

1. One-line verdict with confidence.
2. A two- or three-sentence summary: the story, and the single biggest reason for the verdict.
3. A scorecard table: check | finding (with period and number) | PASS/CAUTION/FAIL.
4. Up to five bullets: key risks, the next event and date, and what would change the verdict.
5. Sources: a list of the pages actually used, as links.

## 6. Output for the scanner page (JSON)

When asked to write the review for the scanner, produce one object:

```json
{
  "market": "ASX",
  "code": "PLS",
  "name": "Pilbara Minerals",
  "date": "2026-10-26",
  "verdict": "SEPA candidate",
  "confidence": "medium",
  "summary": "Two or three sentences.",
  "catalyst": "One sentence, or empty",
  "scorecard": [
    {"check": "Earnings", "finding": "1H FY26 EPS +48% vs 1H FY25; accelerating from +22%", "result": "PASS"}
  ],
  "risks": ["Up to five short bullets"],
  "next_event": "FY26 half-year results, 20 Feb 2027",
  "hold_through_event": "ONLY WITH A PROFIT CUSHION",
  "sources": [{"title": "1H FY26 results (ASX announcement)", "url": "https://..."}]
}
```

- `verdict` must be one of "SEPA candidate", "Watch only" or "Reject".
- `result` must be one of "PASS", "CAUTION" or "FAIL". Give all 11 checks in the order above, and use
  "n/a" in the finding for checks that don't apply.
- Keep each finding under 160 characters.
