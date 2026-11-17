"""LEAN REGIME VOTE  (strategy id: lean_regime_vote, version 1.0, frozen 2026-11-17)

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
"""
from __future__ import annotations
import dataclasses
import datetime as dt
import json
import os

from . import reports, prices, context, regime_book
from .regime_book import RegimeParams
from .book import risk_report

STRATEGY_ID = "lean_regime_vote"
VERSION = "1.0"


def LeanParams(**overrides) -> RegimeParams:
    """The frozen parameter set. Pass overrides only for research variants."""
    base = dict(
        regime_method="text", regime_k=10, force_mode="",
        mom_theme=False, mom_sector=True, mom_cat=True,
        fade_theme=True, fade_new2=False, fade_long34=False, fade_cat_down=True, fade_sector=False,
        hold_theme=5, hold_sector=10, hold_cat=20, max_cat_per_day=2,
        stop_atr=2.0, risk_per_atr=0.004, max_notional=0.20, gross_cap=1.2,
        daily_loss_halt=0.02, dd_halve=0.06, dd_stop=0.12, max_positions=10,
        max_atr=0.07, min_price=5.0, cost_bps=10.0, hedge_cost_bps=2.0, hedge=True,
    )
    base.update(overrides)
    return RegimeParams(**base)


def load_archive(cache_dir: str = "data/reports"):
    """All briefings: {date: plays}, {date: text}. Downloads what is missing."""
    secs = reports.load_sections(cache_dir=cache_dir)
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    T = {d: reports.html_to_text(reports.fetch_report_html(d, cache_dir)) for d in S}
    return S, T


def backtest(start: dt.date | None = None, end: dt.date | None = None, equity0: float = 100_000.0, params: RegimeParams | None = None,
             out_dir: str = "results", tag: str = STRATEGY_ID):
    """Run the strategy over the archive; write results/<tag>.json and results/<tag>_risk.json; return (result, risk)."""
    p = params or LeanParams()
    S, T = load_archive()
    start = start or min(S) + dt.timedelta(days=1)
    end = end or max(S)
    res = regime_book.run(S, T, start, end, p, equity0=equity0)
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end))
    risk = risk_report(res, spy)
    res["strategy"] = {"id": STRATEGY_ID, "version": VERSION, "params": dataclasses.asdict(p)}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(f"{out_dir}/{tag}.json", "w"), indent=1, default=str)
    json.dump(risk, open(f"{out_dir}/{tag}_risk.json", "w"), indent=1)
    return res, risk


def current_mode(report_date: dt.date | None = None, params: RegimeParams | None = None):
    """Regime vote for the newest published report (or a given date), using only reports up to it."""
    p = params or LeanParams()
    rdate = report_date or reports.latest_available_report()
    hist = [d for d in reports.list_archive_dates() if d <= rdate][-max(p.regime_k, 25):]
    texts = {d: reports.html_to_text(reports.fetch_report_html(d)) for d in hist}
    regs = {d: context.regime(texts[d]) for d in hist}
    mode = regime_book.modes_for(regs, p)[rdate]
    return rdate, mode, regs, texts


def orders(report_date: dt.date | None = None, equity: float = 100_000.0, params: RegimeParams | None = None) -> dict:
    """Orders for the next session implied by the newest report. Sizes use the last close before the report date."""
    p = params or LeanParams()
    rdate, mode, regs, texts = current_mode(report_date, p)
    text = texts[rdate]
    sec = reports.parse_retail_section(text, rdate)
    stances = context.sector_stances(text); cats = context.catalysts(text)
    from .mapping import map_play
    sig = []
    if mode == "MOMENTUM":
        sig += [("MOM_SECTOR", e, 1, p.hold_sector, 0.5) for e, v in stances.items() if v == 1]
        sig += [("MOM_CAT", t, 1, p.hold_cat, 0.5) for t, d in cats if d == 1][: p.max_cat_per_day]
    elif mode == "FADE":
        s1, r1 = map_play(sec.plays[0].name) if sec.plays else (None, 0)
        if p.fade_theme and s1 and r1:
            sig.append(("FADE_THEME", s1, -r1, p.hold_theme, 1.0))
        sig += [("FADE_CATDOWN", t, 1, p.hold_cat, 0.5) for t, d in cats if d == -1][: p.max_cat_per_day]
    today = dt.date.today()
    out, net = [], 0.0
    for leg, sym, side, hold, scale in sig:
        try:
            d = prices.daily_map(prices._fetch(sym, "1d", rdate - dt.timedelta(days=45), today))
            last = max(k for k in d if k <= rdate); pc = d[last][3]; atr = prices.atr_pct(d, last + dt.timedelta(days=1))
        except Exception:
            out.append({"leg": leg, "symbol": sym, "skipped": "no price data"}); continue
        if atr is None or atr > p.max_atr or pc < p.min_price:
            out.append({"leg": leg, "symbol": sym, "skipped": f"ATR {atr}"}); continue
        notional = min(equity * p.risk_per_atr / atr, equity * p.max_notional) * scale
        net += side * notional
        out.append({"leg": leg, "symbol": sym, "side": "BUY" if side > 0 else "SELL", "qty": int(notional / pc), "notional": round(notional), "ref_close": pc,
                    "atr10": round(atr, 4), "stop_pct": round(p.stop_atr * atr, 4), "exit_after_sessions": hold})
    return {"strategy": STRATEGY_ID, "version": VERSION, "report_date": rdate.isoformat(), "mode": mode,
            "votes_rate_dir": [regs[d]["rate_dir"] for d in sorted(regs)[-p.regime_k:]], "macro_subtitle": regs[rdate]["subtitle"],
            "sectors": stances, "catalysts": cats, "retail_top": [q.name for q in sec.plays], "orders": out, "spy_hedge_notional": round(-net)}
