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
scripts/run_backtest.py all variants -> results/*.json, results/summary.json
scripts/make_plan.py    next-session plan from the newest available report
data/retail_plays.json  parsed retail sections for all 98 reports (committed)
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
