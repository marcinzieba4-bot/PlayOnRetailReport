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
scripts/run_backtest.py all variants -> results/*.json, results/summary.json
scripts/run_weekly.py   weekly fade variants, all rolling phases -> results/weekly_summary.json
scripts/run_book.py     book leg combinations -> results/book_summary.json
scripts/run_ls.py       long/short with risk rules -> results/ls_risk_report.json
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
7. On a weekly horizon do **not** buy the #1 theme: it lags SPY by ~1.4% over the next week in
   this archive. The weekly trade is the fade (short #1 / long SPY, or long #2), with the same
   small-sample caveat (11 independent weeks).
