# Lean Regime Vote — strategy specification

```
LEAN REGIME VOTE  (strategy id: lean_regime_vote, version 1.0, frozen 2026-11-17)

A market-neutral overlay driven by the ZembiHF daily Market Intelligence Briefing.

Regime (no price or yield level anywhere):
    For each report, read the US macro block: rate_dir = -1 (cut / easing words), 0 (hold),
    +1 (hike / tightening words); and the capital-flows block: liq = -1 tightening, +1 easing.
    Vote over the last 10 reports:  score = mean(rate_dir) + 0.5 * mean(liq)
        MOMENTUM  if score <= -0.34        FADE  if score >= +0.34        NEUTRAL otherwise

Positions (all from report D, traded at the next session's open, flat by time exit):
    MOMENTUM : long each sector ETF the report marks "Bullish"           hold 10 sessions, half size
               long up to two "↑" catalysts from High-Conviction Stock Catalysts   hold 20, half size
    FADE     : short the #1 "What Retail Is Playing" theme (any type)   hold 5, full size
               long up to two "↓" catalysts (contrarian)                 hold 20, half size
    NEUTRAL  : nothing new.
    (The "#1 short" leg is kept for reproducibility; over three years it is flat and the
     recommended variant turns it off: LeanParams(fade_theme=False).)

Risk:
    size: one ATR10 move = 0.4% of equity per position, cap 20% of equity per name
    stop 2.0 ATR10 on daily high/low (gap-through filled at the open); time exit at the hold
    gross cap 120%; max 10 positions; one position per symbol
    daily loss halt 2% -> liquidate, no entries for the rest of the ISO week
    size halved past -6% drawdown from peak, no new entries past -12%
    SPY hedge resized every close to the book's net dollar exposure
    costs 10 bp round trip per position, 2 bp on hedge changes

Point-in-time: the briefing dated D is published ~13:17 ET on D; everything uses report D
for session D+1 (a Friday/weekend report serves Monday; a report older than 3 days serves
nothing).

Backtest (Nov 2023 -> Nov 2026, 778 reports, $100k): +20.1%, ann. vol 5.2%, Sharpe 1.18,
Sortino 1.89, max DD -4.9%, beta 0.00, 329 trades, 115 stops, 3 halts. Un-gated control
-1.3%, regime-inverted control +1.5%. See README sections 12-17 and docs/LEAN_REGIME_VOTE.md.
```

## Files

- `retailplay/lean_regime_vote.py` — frozen parameters (`LeanParams()`), `backtest()`, `orders()`, `current_mode()`
- `scripts/lean_regime_vote.py` — CLI: `backtest`, `plan`, `controls`
- engine: `retailplay/regime_book.py`; regime and report readers: `retailplay/context.py`, `retailplay/reports.py`; mapping: `retailplay/mapping.py`; risk stats: `retailplay/book.py::risk_report`
- results: `results/lean_regime_vote.json`, `results/lean_regime_vote_risk.json`, `results/lean_regime_vote_report.html`, `results/lean_vs_spy.html`

## Data

- Briefings: `https://zembihf.xyz/reports/archive/YYYY-MM-DD.html` (published ~13:17 ET), cached in `data/reports/` (git-ignored, re-downloaded on demand)
- Prices: Yahoo Finance daily bars, cached in `data/prices/` (git-ignored)

## Change log

- 1.0 (2026-11-17): frozen after the Nov 2023 → Nov 2026 backtest (README sections 12–17).
