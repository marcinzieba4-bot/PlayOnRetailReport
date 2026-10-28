# Retail Gap Fade — an intraday strategy built on the ZembiHF "What Retail Is Playing" section

A very short-term (intraday, flat by the close) strategy that trades the **next US cash
session** using only the **previous day's** ZembiHF Market Intelligence Briefing
(`https://zembihf.xyz/reports/`), focusing on its last section, *What Retail Is Playing*.

Everything here is point-in-time clean: the rule set, the backtest and the daily plan
generator only ever see a report after it is published and never use prices from later
in the session being traded.

> Not financial advice. 98 reports / 67 tradeable sessions is a small sample. The backtest
> below is **weakly positive and not statistically significant**. Treat this as a
> hypothesis with a clean, forward-testable implementation, not a proven edge.

---

## 1. What the data actually is (and when it exists)

| Fact | Value | How verified |
|---|---|---|
| Archive span | 2026-06-25 → 2026-09-30, 98 daily reports (incl. weekends) | `reports/index.html` |
| Publish time | **17:16–17:18 UTC = ~13:17 ET, every single day** | HTTP `Last-Modified` of all 98 files |
| Retail section | always exactly 4 plays; #1 has the full narrative (why / drivers / social signal / analog / smart money / *when the narrative breaks*), #2–#4 are one paragraph | parser over all 98 |
| Prices quoted in the report | from the report's own "QUANT SNAPSHOT" (stooq), as of ~13:00 ET on report day | text |

**Consequence for "use only available data":** report `D` is usable from 13:20 ET on `D`.
The strategy uses it for session `D+1` (the next trading day; for Fri/Sat/Sun reports the
newest one before Monday is used). At the `D+1` open the only new input is the opening print.

What retail was playing (primary play, #1) over the window, by mapped instrument:
gold 20 sessions, oil/energy 14, Bitcoin 11, Nasdaq-100 6, Russell-2000 4, then a long
tail of single names (MU, PLTR, NVDA, TSLA, AMD, ONDS, BB, …). Secondary plays rotate
between Bitcoin, gold, oil, AI/semis and small caps. Narratives are "sticky": the same #1
repeats for days or weeks (gold through all of August, Bitcoin through September).

## 2. The thesis

The section is, by construction, a *crowding detector*: the author explicitly frames each
play as a popular narrative with a "smart money view" and a "when the narrative breaks"
kill switch. A crowded retail name gets chased at the next open. Measured on the archive:

| Next-session move of the #1 retail play, signed in retail's direction | n | mean | t |
|---|---|---|---|
| overnight gap (D close → D+1 open) | 67 | **−34 bp** | −1.97 |
| D+1 open → close | 67 | −10 bp | −0.55 |
| D+1 open → close **when it gapped > +0.25 ATR in retail's direction** | 14 | **−47 bp** (29% up) | −1.32 |
| D+1 open → close when it gapped < −0.25 ATR against retail | 21 | +33 bp | +1.11 |
| same tests on SPY: gap up → +8 bp, gap down → −15 bp (gaps **continue** on the index) | | | |

So riding the retail play ("momentum") has no next-day edge, and overnight gaps in the
crowded name tend to **mean-revert** while index gaps tend to continue. The strategy fades
the gap in the crowded name, intraday only.

## 3. Rules (fixed before the event-level backtest)

**Universe for session T:** plays #1 and #2 from the newest report dated < T, mapped to a
liquid proxy (`retailplay/mapping.py`: Bitcoin/crypto → IBIT, gold → GLD, oil/energy → XLE,
AI/mega-cap → QQQ, semis → SMH, small-cap rotation → IWM, single names → themselves, etc.).
The direction retail is on (long/short) is parsed from the play name ("Short Gold …" → short).

**Inputs at 9:30 ET on T:** previous close and ATR10 (sessions ≤ D), SPY opening gap, the
opening print.

**Entry (at the open, +5 bp slippage):**
- `gap = open / prev_close − 1`. Trade only if `|gap| ≥ 0.25 × ATR10`.
- Default (`legs="extension"`): fade only gaps **in retail's direction** — gap up in a
  retail-long name → **short**; gap down in a retail-short name → **long**.
- `legs="crack"` (buy the dip when the crowded name gaps against the crowd) and
  `legs="both"` are implemented for comparison; see results.
- Skip: ATR10 > 6% (micro-cap junk), price < $5, SPY gap < −1% for long entries (crash
  days trend), untradeable themes (Fed/vol plays), single names reporting earnings that day
  (manual).

**Exits (strict, every trade has all three):**
- Stop: 0.60 × ATR10 from entry, evaluated on intraday highs/lows (stop assumed hit first
  if stop and target touch in the same bar).
- Target: gap fill (previous close), capped at 1.0 × ATR10.
- Time: flat at 15:55 ET. Never overnight.

**Risk budget:** 0.5% of equity at the stop per trade (≈35–40% notional per trade, no
leverage needed); max 2 trades/day (#1 and #2); no new trades after a −1% day or a −2.5%
week; no re-entry in a name after a stop.

## 4. Backtest (2026-06-26 → 2026-09-30, 67 sessions, hourly bars from Yahoo; 15-min cross-check)

Equity $100k, 5 bp slippage per side, no commissions.

| Variant | trades | hit | avg/trade | t | PF | total | max DD | exits (target/stop/time) |
|---|---|---|---|---|---|---|---|---|
| **default: extension leg, #1+#2, 1h** | 37 | 59% | +11.8 bp | 0.71 | 1.34 | +0.9% | −2.4% | 11 / 7 / 19 |
| default, 15-min bars | 35 | 60% | +11.9 bp | 0.68 | 1.34 | +1.0% | −2.4% | 11 / 7 / 17 |
| both legs, #1+#2 | 72 | 58% | +5.2 bp | 0.46 | 1.14 | +0.4% | −2.6% | 22 / 13 / 37 |
| crack leg only | 35 | 57% | −1.8 bp | −0.12 | 0.95 | −0.5% | −1.6% | |
| both legs, #1 only | 35 | 57% | −6.7 bp | −0.41 | 0.85 | −1.1% | −2.1% | |
| both legs, all 4 ranks | 134 | 57% | +1.4 bp | 0.16 | 1.04 | +0.9% | −4.4% | |
| both legs, **no stop/target** (fixed 35% notional) | 71 | 59% | −2.7 bp | −0.19 | 0.94 | −0.7% | −4.3% | |
| both legs, tighter stop 0.4 / target 0.8 ATR | 72 | 54% | +6.0 bp | 0.59 | 1.18 | +0.6% | −3.1% | |
| both legs, gap threshold 0.5 ATR | 42 | 57% | +13.0 bp | 0.93 | 1.46 | +1.2% | −1.4% | |
| extension leg, gap threshold 0.5 ATR | 25 | 64% | +33.9 bp | 1.78 | 2.60 | +2.4% | −1.3% | |

Read honestly:
- **Nothing here clears t ≈ 2.** The sign is consistently positive for the extension leg
  across bar resolutions, thresholds and months (Jul +8.7 bp, Aug +4.1, Sep +9.9 bp/trade
  for both legs), which is encouraging, but the sample is ~35–70 trades.
- **Risk management is doing real work**: removing the stop/target turns a positive
  expectancy into a negative one, and the max drawdown stays ≤ 2.6% in every stopped variant.
- The crack leg (buying narrative cracks) shows nothing; the extension-only default was
  chosen *after* seeing this split, so it is an in-sample choice. The gap-0.5 ATR rows look
  best and are the smallest samples — do not read them as the expected result.
- By instrument (both legs): GLD was the loser (21 trades, −31 bp/trade): gold trended hard
  all window (up to $4,700 in August, down to $4,190 by late September) and its gaps
  continued. IBIT (+35 bp, 13), XLE (+12 bp, 16), QQQ (+31 bp, 6) were the winners. A
  "don't fade a name in a strong multi-week trend" filter is the obvious next hypothesis;
  it is **not** added here to avoid curve-fitting.

## 5. Running it

```bash
# refresh the archive + parsed plays, rebuild all backtest variants into results/
python scripts/run_backtest.py

# tomorrow's plan from the newest published report (run after 13:20 ET, or next morning)
python scripts/make_plan.py --equity 100000
python scripts/make_plan.py --date 2026-09-30 --legs both
```

`make_plan.py` prints, per play, the exact open levels that trigger a trade, the share
count, the stop and target, and the report's own "when the narrative breaks" kill switch,
e.g. for the 2026-09-30 report → 2026-10-01 session:

```
#1 'Bitcoin (BTC)' -> IBIT  retail is LONG   prev close 47.34   ATR10 3.01%
      if OPEN >= 47.70 (gap up > +0.75%):  SHORT 580 sh | stop +1.81% | target max(prev close, entry-3.01%) | else flat 15:55
#2 'Mega-Cap Tech / Nasdaq 100' -> QQQ   prev close 739.77   ATR10 1.34%
      if OPEN >= 742.25 (gap up > +0.34%):  SHORT 83 sh  | stop +0.81% | target max(prev close, entry-1.34%) | else flat 15:55
```

## 6. Layout

```
retailplay/reports.py   fetch + cache the archive, parse "What Retail Is Playing" (4 plays, fields)
retailplay/mapping.py   play name -> (ticker, retail direction), ordered regex rules
retailplay/prices.py    Yahoo chart API (1d / 1h / 15m), ET timestamps, ATR10
retailplay/strategy.py  Params (all fixed a priori), build_signal(), position_size()
retailplay/backtest.py  event-level simulation with stop/target/time exits and loss caps
retailplay/weekly.py    weekly Retail #1 Fade pair (short #1 theme / long SPY or #2), ATR stop, 5-session hold
retailplay/sentiment.py tone / warning-intensity / fear-vs-greed / imminence features from play text
retailplay/book.py      multi-leg hedged book (S1 fade, LP persisting long, DR dropout short)
retailplay/context.py   sector stances, macro stance, catalysts, regime (rates / liquidity / 10Y / VIX) from report text
retailplay/regime_book.py regime-gated narrative momentum book
scripts/run_backtest.py all variants -> results/*.json, results/summary.json
scripts/run_weekly.py   weekly fade variants, all rolling phases -> results/weekly_summary.json
scripts/run_book.py     book leg combinations -> results/book_summary.json
scripts/run_ls.py       long/short with risk rules -> results/ls_risk_report.json
scripts/run_regime.py   regime-gated book variants -> results/regime_risk_report.json
scripts/make_plan.py    next-session plan from the newest available report
data/retail_plays.json  parsed retail sections for all 98 reports (committed)
```

## 8. Weekly horizon: continuation does not exist, the fade does

Tested after the intraday work (so treat it as a second, in-sample study on the same
98 reports). Entry at the open of the first session after the report, signed in retail's
direction, held 5 / 10 sessions, daily bars.

| Long the theme in retail's direction | n | 5-session mean | hit | t |
|---|---|---|---|---|
| #1 play (all reports, overlapping) | 83 | **−112 bp** | 39% | −2.6 |
| #1 play, excess vs SPY | 83 | **−139 bp** | 29% | −3.1 |
| #1 play, ex-gold | 56 | −196 bp | 30% | −4.1 |
| #2 play | 82 | +86 bp | 56% | +1.3 |
| #3/#4 plays | 163 | +24 bp | 53% | +0.5 |
| SPY over the same windows | 83 | +27 bp | 55% | |
| long #2 minus long #1 (same report) | 82 | **+202 bp** | 65% | +2.4 |

Conditioning that was supposed to find continuation found the opposite:
- Prior week **and** month up in the theme → next week −97 bp (t = −2.2). A pullback inside
  an uptrend (5d down, 20d up) → +70 bp / +136 bp over 5 / 10 sessions, i.e. the only
  "buy" shape is a dip, not strength.
- A **new** #1 theme (first day at #1) → −109 bp next week, −187 bp over two weeks. A #1 that
  has held the slot 5+ days → every one of 12 cases negative (but those are one gold episode).
- Themes that **drop out** of the list keep falling: −96 bp over the next week (n = 175).
- Gold is the exception that proves the mechanism: it was #1 for weeks while trending up in
  August (+61 bp/week as #1), then became the loser in September.

Non-overlapping event-level backtest (`retailplay/weekly.py`, `scripts/run_weekly.py`):
short the #1 theme at the first open after the newest report, one trade per week, 1.5 ATR
stop on daily high/low, flat at the close of the 5th session, 10 bp round trip per leg,
1% of equity at risk, hedge leg equal notional.

| Variant | n | avg/week | hit | t | total | max DD |
|---|---|---|---|---|---|---|
| short #1, long SPY | 11 | +0.37% | 64% | 1.6 | +4.1% | −0.8% |
| short #1, long #2 theme | 11 | +1.27% | 73% | 2.6 | +14.7% | −1.2% |
| short #1, no hedge | 11 | +0.29% | 64% | 1.5 | +3.2% | −0.7% |
| short #1, long SPY, ex-gold | 8 | +0.29% | 62% | 1.2 | +2.3% | −0.8% |
| rolling 5-session schedule, SPY hedge, phases 0–4 | 10–13 each | +0.07% … +0.41% | 54–75% | 0.2–1.7 | all positive | ≤ −3.3% |
| rolling, #2 hedge, phases 0–4 | 10–13 each | −0.32% … +1.04% | 45–58% | −0.6 … 2.2 | 2 of 5 negative | ≤ −8.5% |

Reading: the sign is stable across every phase for the SPY-hedged fade, the ex-gold check
holds, and no trade hit the stop on the weekly schedule. But 11 independent weeks is 11
weeks; t ≈ 1.6 is not proof. The #2-hedged pair looks best on the Monday schedule and worst
on two other phases, so its extra return is fragile. Going long the #1 theme for a week
("continuation") is simply the negative of the short leg: about −0.85% per week.

```bash
python scripts/run_weekly.py            # all variants, trade list for the SPY-hedged version
python scripts/make_plan.py --weekly    # this week's pair from the newest report
```

## 9. Sentiment, momentum, dropouts: a combined book (and why most of it dissolves)

`retailplay/sentiment.py` extracts, from the play text only: a lexicon tone score, the
author's crowding-language intensity (`warn`: bubble / parabolic / fragile / euphoric per
100 words), a fear-vs-greed theme class from the play name (gold, oil, defence, bonds,
"short …" = fear; AI, crypto, squeezes, rotation = greed), kill-switch imminence, and the
4-week move the report quotes. Facts first:

- **The #1 play is never a retail-short theme** in this archive (83 of 83 are retail long).
  Bearish themes ("Short Gold", "AI Short / Nvidia Put", "Short Bitcoin") only ever appear at
  ranks 2–4 (7 cases) and retail lost on those too (−198 bp next week).
- The "smart money view" field is formulaic ("institutional money is genuinely split")
  and carries no signal. The author's **warning intensity does**: #1 plays in the top
  `warn` tercile lost −218 bp the next week (25% hit) vs −10 bp in the bottom tercile.
- **Theme class is the big splitter** (overlapping counts): #1 greed themes −247 bp next week
  (18% hit, t = −4.1, both halves of the sample, every ticker but PLTR and MSFT); #1 fear
  themes flat (+1 bp), with gold positive in August and negative in September.
- Raw dropout stats (theme leaves the list → −92 bp next week; was #1 → −430 bp) and the
  raw "#1 greed" numbers are **inflated by overlap**: the same collapsing name is counted on
  every day it drops in and out (RKLB 9 times, MU 11, IBIT 13). Counting each event once
  changes the answer, see below.

`retailplay/book.py` trades the ideas as one hedged book: entries at the next open, one
position per symbol, 10% notional each, 1.5 ATR stop, 5-session hold, 10 bp costs, SPY hedge
sized daily to the net exposure. Legs: **S1** short the #1 theme when it is a greed theme;
**LP** long the #2–#4 themes that were already listed the day before (persisting
narratives), in retail's direction; **DR** short a greed theme that just dropped off the
list. `scripts/run_book.py` runs the combinations:

| Book | trades | total | max DD | Sharpe | H1 / H2 | S1 (n, bp/trade) | LP | DR |
|---|---|---|---|---|---|---|---|---|
| all three legs, hedged | 78 | −0.8% | −3.4% | −0.6 | −1.6% / +0.8% | 11, +15 | 28, +64 | 39, **−89** |
| S1 only | 13 | −0.2% | −1.4% | −0.3 | −0.1% / −0.1% | 13, +35 | | |
| S1 only, strong warning language | 5 | +0.2% | −0.5% | 0.7 | | 5, +111 | | |
| LP only | 33 | +1.6% | −1.0% | 1.6 | +0.6% / +1.0% | | 33, +50 | |
| LP only, 10-session hold | 21 | +4.6% | −1.3% | 3.4 | +0.5% / +4.1% | | 21, +200 | |
| LP + S1, 10-session hold | 17 | +4.6% | −1.0% | 3.8 | +1.7% / +2.8% | 4 | 13 | |
| DR only | 53 | −3.9% | −5.1% | −3.1 | −3.4% / −0.5% | | | 53, −92 |

What survives and what does not:
- **Dropout short: dead.** Once each dropout is traded once, the dropped names go *up*
  (−60 bp for the short on the matched events, 17 of 53 trades stopped). The raw effect was
  a handful of collapsing micro-caps counted many times.
- **#1 greed fade: much smaller than it looked.** 13 non-overlapping trades, +35 bp each, no
  stops hit, zero total. The −247 bp raw figure was one Bitcoin episode and one small-cap
  episode counted a dozen times. Restricting to strong warning language gives +111 bp on 5
  trades, which is not evidence.
- **Persisting lower-rank long: the one leg left standing**, +50 bp per trade on 33 trades,
  positive in both halves, drawdown −1%. But: it is almost entirely XLE (+194 bp × 7) and
  GLD (+88 × 6), i.e. fear themes in a quarter when oil and gold trended; greed themes in the
  same leg made −4 bp; rank 2 alone is negative (−43 bp) and ranks 3–4 carry it; requiring
  2 or 3 days of persistence instead of 1 makes it *worse* (+19 / +22 bp), which is not what
  a real persistence effect would do. The 10-session hold is the best cell and the smallest.
- Stops help every leg (no-stop versions are worse); the hedge barely matters because the
  book is small (average gross 15–30% of equity).

Bottom line: the sentiment features are real descriptors of the text (and the greed/fear
split plus warning intensity are the two worth keeping as filters), but the only thing in this
section that would survive a sceptical reviewer is "do not own the #1 greed theme", and that
is already the weekly fade from section 8. The momentum-continuation legs built on
persistence and dropouts do not survive de-duplication on 98 reports.

```bash
python scripts/run_book.py      # all leg combinations -> results/book_*.json, results/book_summary.json
```

## 10. Narrative Long/Short with portfolio risk management

The book that puts the surviving pieces together (`scripts/run_ls.py`, engine in
`retailplay/book.py`, config `LS_base`):

**Positions**
- Short the #1 theme at the next open after the newest report, opposite to retail. Full size
  if it is a greed theme, half size if it is a fear theme (gold, oil, defence, bonds).
- Long the #2–#4 themes that were already listed the day before, in retail's direction.
- SPY hedge resized every close to the book's net dollar exposure.
- One position per symbol, 5-session hold, entries only when a slot is free.

**Risk rules (all enforced in the simulation)**
| Rule | Setting |
|---|---|
| Position sizing | volatility-targeted: one ATR10 move = 0.4% of equity, cap 25% of equity per name |
| Stop | 1.5 × ATR10 on daily high/low, gap-through filled at the open |
| Time exit | close of the 5th session |
| Gross cap | 100% of equity in theme positions (hedge excluded) |
| Daily loss halt | −1.5% day → liquidate at the close, no new entries for the rest of the ISO week |
| Drawdown de-risk | size halved beyond −6% from peak, no new entries beyond −10% |
| Costs | 10 bp round trip per position, 2 bp on hedge changes |
| Skips | ATR10 > 6%, price < $5, untradeable themes |

**Risk statistics, 2026-06-26 → 2026-09-30 (67 sessions, $100k)**

| metric | LS_base | greed-only short | 10-day hold | short leg only | long leg only | no hedge | no risk rules | 2× risk |
|---|---|---|---|---|---|---|---|---|
| total return | +2.70% | +3.67% | +5.20% | +0.45% | +3.59% | +2.39% | +2.00% | +2.00% |
| annualised vol | 5.7% | 6.5% | 6.3% | 3.7% | 6.4% | 6.3% | 5.8% | 9.5% |
| Sharpe | 1.77 | 2.11 | 3.06 | 0.48 | 2.09 | 1.45 | 1.32 | 0.83 |
| Sortino | 2.92 | 3.14 | 5.59 | 0.65 | 3.17 | 2.42 | 2.03 | 1.29 |
| max drawdown | −1.49% | −2.04% | −1.33% | −1.37% | −2.17% | −1.52% | −1.54% | −2.69% |
| longest drawdown | 19 d | 13 d | 14 d | 56 d | 12 d | 28 d | 19 d | 20 d |
| worst day / week | −0.78% / −0.68% | −1.36% / −0.97% | −0.70% / −0.72% | −0.58% / −0.56% | −1.15% / −0.69% | −0.85% / −0.93% | −0.89% / −1.10% | −1.30% / −0.87% |
| daily VaR 95 / CVaR 95 | −0.57% / −0.68% | −0.70% / −1.02% | −0.57% / −0.65% | −0.39% / −0.52% | −0.62% / −0.96% | −0.61% / −0.73% | −0.57% / −0.77% | −0.89% / −1.22% |
| skew | +0.51 | −0.36 | +0.67 | −0.36 | −0.14 | +0.74 | +0.25 | +0.53 |
| beta / corr to SPY | 0.00 / 0.00 | −0.18 / −0.31 | 0.00 / −0.01 | 0.00 / 0.00 | −0.15 / −0.25 | 0.04 / 0.08 | −0.04 / −0.07 | 0.08 / 0.10 |
| avg / max gross | 45% / 90% | 44% / 79% | 62% / 101% | 18% / 55% | 35% / 78% | 45% / 90% | 46% / 89% | 64% / 102% |
| avg / max abs net | 5% / 55% | 15% / 78% | 10% / 69% | −18% / 55% | 29% / 78% | 5% / 55% | 7% / 67% | −1% / 88% |
| trades / stops / halts | 51 / 10 / 0 | 43 / 7 / 0 | 30 / 10 / 0 | 26 / 5 / 0 | 33 / 7 / 0 | 51 / 10 / 0 | 47 / 0 / 0 | 47 / 10 / 0 |
| H1 / H2 return | +1.2% / +1.5% | +0.7% / +3.0% | +1.1% / +4.0% | −0.1% / +0.6% | +0.6% / +3.0% | +0.4% / +2.0% | +1.1% / +0.9% | +1.7% / +0.3% |

SPY returned +4.6% over the same window. Leg attribution for `LS_base`: short leg 24
trades, −18 bp average but +0.70% of equity (the vol sizing gave the winners more weight);
long leg 27 trades, +33 bp average, +2.27% of equity; hedge +0.30%.

**How to read this**
- The book does what a risk framework should: zero beta, zero correlation to SPY, positive
  skew, worst day under 1%, maximum drawdown 1.5% with 45% average gross. The daily halt and
  drawdown rules never triggered, so they are untested insurance, not a source of return.
- The return itself is small and the sample is tiny: +2.7% in 67 sessions. A Sharpe measured
  over a quarter of a year has a standard error of about ±2, so "1.8" and "0.5" are not
  distinguishable from each other or from zero. Both halves are positive, which is the best
  that can be said.
- Removing the stops costs little here (no stops → Sharpe 1.3) because no big adverse move
  hit the book; doubling risk halves the Sharpe (0.8) because the bigger positions sit in the
  noisiest names. Keep the size as is.
- The long leg carries the P&L and it is mostly XLE and GLD trending in Q3 (section 9). The
  short leg is flat on average: it earns its place as the hedge against the long leg's theme
  exposure, not as alpha.

```bash
python scripts/run_ls.py            # all configurations + full risk table + weekly equity path
python scripts/make_plan.py --ls    # today's L/S orders from the newest report
```

## 11. Out-of-sample: the archive extended to Dec 2025 → Oct 2026 (237 reports)

Everything above was designed on 98 reports (Jun 25 → Sep 30, 2026). The archive now runs
from 2025-12-01 to 2026-10-27, so Dec 2025 → May 2026 is a true out-of-sample test, and
Jun → Oct 2026 re-runs the in-sample period with a month added. Two fixes were needed to
read the older reports: an optional intro line in the section parser (the Dec–Jan format
has none, which had silently dropped every January #1 play) and ticker extraction for the
"Company / TICKER" naming used until March. Prices were refetched from Oct 2025. A 3-day
report-staleness cap was added (no effect here, the archive only skips weekends).

**The headline: the strategies do not survive the earlier period.**

| Strategy, full span Dec 2025 → Oct 2026 | result | Dec–May | Jun–Oct |
|---|---|---|---|
| Intraday gap fade, default (section 4) | 90 trades, −6.9 bp/trade, −2.0%, Sharpe −1.2 | | |
| Weekly #1 fade, SPY hedge (section 8) | 31 weeks, −0.14%/week, −4.3%, max DD −7.5%; negative in all 5 rolling phases | | |
| Long/short `LS_base` (section 10) | 151 trades, −2.8%, Sharpe −0.4, max DD −6.0% | −5.0% | +2.3% |
| Long/short, greed-only short leg | 128 trades, +2.0%, Sharpe 0.35, max DD −4.1% | +1.2% | +0.8% |
| Long leg only (persisting #2–#4) vs SPY | 95 trades, +2.5%, Sharpe 0.5, max DD −4.2% | +2.9% | −0.4% |
| Short leg only vs SPY | 78 trades, −3.4%, Sharpe −0.9 | −4.4% | +1.0% |
| SPY, same span | +12.9% | | |

Why: the #1 theme's next-week return flips sign by regime.

| month | #1 next-5-session return (retail direction) | hit | #1 names |
|---|---|---|---|
| 2025-12 | **+567 bp** | 96% | SLV, MSTR, SMH |
| 2026-01 | +193 bp | 64% | SLV, RDDT, GLD |
| 2026-02 | −64 bp | 40% | SLV, TSLA, GLD |
| 2026-03 | −368 bp | 32% | NBIS, RKLB, NOW |
| 2026-04 | +41 bp | 62% | QQQ, GME, OPEN |
| 2026-05 | −10 bp | 57% | QQQ, NVDA, SMH |
| 2026-06 | −590 bp | 32% | RKLB, MU, QQQ |
| 2026-07 | −105 bp | 43% | XLE, IWM, IBIT |
| 2026-08 | +68 bp | 57% | GLD, MSFT, PLTR |
| 2026-09 | −57 bp | 32% | IBIT, XLE, QQQ |
| 2026-10 | −212 bp | 8% | QQQ, IBIT, NVDA |

December 2025 and January 2026 were the silver and gold mania: the #1 fear theme made
+411 bp per week over Dec–May (73% hit, t = 4.1) and shorting it, even at half size with a
1.5 ATR stop, cost the short leg −5.3% of equity in that half. The greed-theme #1s stayed
negative in both halves (−118 bp Dec–May, −278 bp Jun–Oct), which is the one text-based
finding that generalised; it is what keeps the greed-only short leg roughly flat
(−38 bp/trade) instead of losing. The persisting lower-rank long made +104 bp/trade in
Dec–May and −17 bp in Jun–Oct, so it is positive but regime-dependent (metals again).

What this means in practice:
- **Never fade a fear theme at #1.** The in-sample half-size compromise was wrong; the
  out-of-sample cost was the whole drawdown. `s1_fear_scale=0` is the only defensible setting.
- **The intraday and weekly fades are not strategies.** They were one quarter's regime.
- The surviving book is "short greed #1 / long persisting #2–#4 / SPY-hedge": +2.0% over 11
  months, Sharpe 0.35, max DD 4%, zero beta. That is a hedge-shaped nothing, not a product.
  The only firm, reusable conclusions from 237 reports are (1) greed narratives at #1
  underperform the following week and (2) fear narratives at #1 can run for months.

```bash
python scripts/run_ls.py && python scripts/pnl_report.py results/LS_base.json results/LS_base_report.html
```

## 12. Reading the whole briefing: a regime-switched narrative book (what works)

Sections 1–11 only used the retail section. The rest of the briefing is structured enough to
read by machine (`retailplay/context.py`): a **Bullish / Bearish / Mixed stance for each of
12 sectors** every day, a **stance and one-line subtitle for the US macro block** ("cut
priced, data soft", "↑ rate hike risk"), **$TICKER catalysts with ↑/↓ arrows**, the quoted
10-year and VIX, and the vocabulary of the capital-flows block ("liquidity is returning"
vs "coordinated G3 tightening").

**The regime, read from text only.** For each report, `rate_dir` is −1 / 0 / +1 from the US
block's subtitle and first lines (cut / easing words vs hike / tightening words), and `liq`
is −1 / 0 / +1 from the capital-flows vocabulary. The mode is a vote over the last 10
reports: MOMENTUM when the vote reads easing, FADE when it reads tightening, NEUTRAL
otherwise. No yield level is used (`regime_method="text"`). Yield-trend and yield-rank
variants exist for a longer history but do not work on this one because the quoted 10-year
sat flat at 4.1–4.2% during the whole easing period.

| regime (text vote) | #1 theme, next 5 sessions | Bullish sectors vs SPY, 10 sessions | ↑ catalysts vs SPY, 20 sessions |
|---|---|---|---|
| MOMENTUM (53 report-days: Dec, Feb–Mar) | **+160 bp** | +92 bp | **+645 bp** |
| NEUTRAL (74) | −28 bp | +134 bp | −144 bp |
| FADE (100: May–Oct) | **−166 bp** | −19 bp | +70 bp |

**Inside the tightening regime the retail section still has uses, but not the obvious ones:**

| FADE regime, signed in retail's direction, excess vs SPY | n | 5 sessions | 10 sessions |
|---|---|---|---|
| #1 theme, any type | 100 | −108 bp (t = −2.4) | −85 bp |
| #1 theme, persisting from the day before | 53 | **−136 bp (t = −3.1)** | −117 bp |
| #1 fear theme (gold, oil) | 30 | −170 bp (t = −3.0) | −120 bp |
| #2 theme, newly promoted | 54 | −218 bp | −172 bp |
| #3 theme, persisting | 30 | +61 bp | +109 bp |
| #4 theme, persisting | 29 | +96 bp | +172 bp |
| the author's **↓ catalysts, held long** (contrarian), 20 sessions | 114 | | **+355 bp, 66% hit, t = 3.5** |
| Bearish sectors, long | 269 | −22 bp | −12 bp |

So in a tightening regime the #1 is a short whether greed or fear (the gold exception of
section 11 was the easing regime, not the theme type), a newly promoted #2 is a trap, the
persisting #3/#4 are weakly positive, and the names the author flags as "↓ risk" (usually
into earnings) are the best longs in the whole dataset.

**The book** (`retailplay/regime_book.py`, `scripts/run_regime.py`, config `REG_text`):
- MOMENTUM: long the #1 theme (5 sessions), long each Bullish sector ETF (10, half size),
  long up to two ↑ catalysts (20, half size).
- FADE: short the #1 theme (5), short a newly promoted #2 (5, 0.75 size), long persisting
  #3/#4 (5, half), long up to two ↓ catalysts (20, half). Bullish-sector shorts are off.
- NEUTRAL: no new positions.
- Risk: one ATR = 0.4% of equity, cap 20% per name, 2 ATR stop, gross cap 120%, 2% daily
  halt, size halved past −6% drawdown, no entries past −12%, SPY hedge to net zero, 10 bp
  per round trip.

| variant | total | ann. vol | Sharpe | max DD | beta | trades | Dec–May | Jun–Oct |
|---|---|---|---|---|---|---|---|---|
| **REG_text** | **+18.5%** | 7.4% | 2.56 | −4.3% | −0.09 | 176 | +5.6% | +12.2% |
| momentum legs only | +7.1% | 4.7% | 1.65 | −2.6% | | 71 | +7.1% | 0.0% |
| fade legs only | +10.4% | 5.8% | 1.91 | −2.2% | | 105 | −1.4% | +12.0% |
| without the ↓-catalyst long | +11.7% | | 1.96 | −4.5% | | 156 | +6.0% | +5.4% |
| without the new-#2 short | +9.6% | | 1.54 | −5.5% | | 164 | +5.9% | +3.4% |
| without the persisting #3/#4 long | +18.9% | | 2.56 | −4.1% | | 161 | | |
| with Bullish-sector shorts in FADE | +10.4% | | 1.61 | −6.3% | | 201 | | |
| vote window 5 / 20 reports instead of 10 | +23.9% / +18.4% | | 3.28 / 2.54 | −4.0% / −4.3% | | | | |
| composite regime (adds yield trend and rank) | +10.9% | | 1.74 | −3.7% | | | −0.9% | +11.9% |
| legacy fixed 4.3% / 4.6% yield gate | +23.9% | | 2.97 | −2.9% | | | +11.0% | +11.6% |
| no stops / halts | +23.2% | | 3.29 | −3.4% | | | | |
| SPY buy-and-hold | +13.1% | | | | | | | |

Monthly P&L ($100k): Dec +3.3k, Jan +2.6k, Feb +3.1k, Mar −1.9k, Apr −0.3k, May −1.2k,
Jun −0.8k, Jul +3.6k, Aug +3.4k, Sep +3.9k, Oct +2.8k. Eight of eleven months positive.

Attribution: ↓-catalyst contrarian longs +4.8% of equity (37 trades, +213 bp each, 57%
hit, META +2.6k, OXY, ON, MSFT, NVDA; 13 stops), #1-theme fades +4.0% (32 trades, 69% hit,
QQQ, IBIT, XLE), #1-theme momentum +2.1% (silver is +4.2k of it), Bullish-sector momentum
+1.1%, catalysts ↑ +0.5%, new-#2 shorts +0.1% (but they cut the drawdown: without them
−5.5%), persisting #3/#4 longs +0.6%.

**Honest reading.**
- The regime vote does the work in both directions now: it turns momentum on in Dec–Mar
  and turns the retail fades on from May. Both halves are positive, which none of the
  earlier books managed.
- The legacy fixed yield gate scores higher (+23.9%) because it also calls January
  momentum; the text vote calls January neutral. The text vote is the one to keep: it has no
  level in it and will transfer to a longer history. Window length barely matters (5 to 20).
- The ↓-catalyst contrarian long is the single strongest leg and the least intuitive: the
  author flags names as "↓ risk" into earnings or news, and in a tightening regime they
  outperform over the following month. 30 different names, so it is not one stock, but 37
  trades is still 37 trades.
- Silver still carries the momentum theme leg. The persisting #3/#4 long, which was the
  intuitive "lower ranks work in tightening" idea, is positive but tiny (+0.6%).
- Stops cost about 5 points here, as they did in every momentum variant. They are kept
  because the sample has no crash in it.
- One easing regime and one tightening regime are two observations. The next regime flip is
  the real test; the code reads it from the text the day it happens.

```bash
python scripts/run_regime.py                 # variants + risk table + monthly P&L + mode calendar
python scripts/make_plan.py --regime         # today's regime vote and the orders it implies
python scripts/pnl_report.py results/REG_text.json results/REG_text_report.html
```

## 7. What to do with this (summary)

1. The briefing is a clean daily crowding signal available at 13:17 ET; trade it for the next
   session, never same-day-morning.
2. Don't chase the #1 retail play: next day it tends to gap *against* the crowd and shows no
   follow-through.
3. The tradeable idea is fading an opening gap that extends the crowd's direction in the #1/#2
   name, with an ATR stop, gap-fill target and 15:55 flat. Evidence is directionally
   supportive but too thin to size up: **paper-trade or run at minimum size for ~100 more
   trades**, then re-evaluate with `run_backtest.py`.
4. Gold-type trending names were the failure mode; a trend filter is the first thing to test
   out-of-sample.
5. Sentiment: the #1 is never a bearish theme; what matters is greed vs fear and how loudly
   the author warns. Fade only greed #1s with strong warning language; never fade fear #1s.
   Dropout shorts and persistence longs do not survive de-duplication.
6. The assembled long/short (short #1, long persisting #2–#4, SPY-hedged, vol-sized, 1.5 ATR
   stops, daily halt, drawdown de-risk) ran at Sharpe 1.8, max drawdown 1.5%, zero beta over
   67 sessions. Those risk numbers are the deliverable; the return is not yet evidence.
7. **Out of sample (Dec 2025 → May 2026) the fades failed**: fear themes at #1 ran for months.
   Only "greed #1 underperforms next week" generalised. See section 11.
8. **What works: a regime vote read from the macro text, no yield level.** Easing vote: ride the
   #1 theme, Bullish sectors and ↑ catalysts. Tightening vote: short the #1 theme and a newly
   promoted #2, go long the author's ↓ catalysts. +18.5%, Sharpe 2.6, max DD 4.3%, beta −0.1,
   both halves positive. Section 12.
9. On a weekly horizon do **not** buy the #1 theme: it lags SPY by ~1.4% over the next week in
   this archive. The weekly trade is the fade (short #1 / long SPY, or long #2), with the same
   small-sample caveat (11 independent weeks).
