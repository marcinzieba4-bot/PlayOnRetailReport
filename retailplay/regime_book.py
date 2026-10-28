"""Regime-Switched Narrative Book.

The briefing's own macro text decides the mode each day:
  MOMENTUM  when the US block has a cut / easing bias (rate_dir <= 0) and the quoted 10Y is
            below `y10_lo`  -> ride the narratives:
              long the #1 retail theme (hold_theme sessions)
              long Bullish sectors vs SPY (hold_sector)
              long ↑ catalysts vs SPY (hold_cat)
  FADE      when the US block has a hike bias (rate_dir == 1) or the quoted 10Y is at or
            above `y10_hi` -> fade them:
              short the #1 retail theme if it is a GREED narrative (never fear)
              short Bullish sectors vs SPY
  NEUTRAL   otherwise: no new theme / sector positions.
All inputs are read from report D and traded at the open of the next session.
Risk: vol-targeted sizing, ATR stop, gross cap, daily halt, drawdown de-risking, SPY hedge
to net zero (sector and catalyst legs are already expressed vs SPY by construction).
"""
from __future__ import annotations
import dataclasses
import datetime as dt
import math
import statistics as st
from collections import defaultdict

from . import prices, reports, context
from .mapping import map_play
from .sentiment import features
from .strategy import plays_for_session
from .book import risk_report  # same daily-series statistics


@dataclasses.dataclass(frozen=True)
class RegimeParams:
    regime_method: str = "text"   # 'text' (no yield level: smoothed rate-direction + liquidity words) | 'composite' | 'ytrend' | 'yrank' | 'fixed'
    regime_k: int = 10            # reports in the smoothing window
    y10_lo: float = 4.3           # only used by regime_method='fixed'
    y10_hi: float = 4.6
    use_rate_dir: bool = True
    use_y10: bool = True
    mom_theme: bool = True
    mom_sector: bool = True
    mom_cat: bool = True
    fade_theme: bool = True       # FADE: short the #1 theme (any narrative type)
    fade_new2: bool = True        # FADE: short a #2 theme that was not listed the day before
    fade_long34: bool = True      # FADE: long persisting #3 / #4 themes
    fade_cat_down: bool = True    # FADE: long the author's ↓ catalysts (contrarian), hold_cat
    fade_sector: bool = False     # FADE: short Bullish sectors (off: no edge)
    fade_greed_only: bool = False
    hold_theme: int = 5
    hold_sector: int = 10
    hold_cat: int = 20
    max_cat_per_day: int = 2
    stop_atr: float = 2.0
    risk_per_atr: float = 0.004
    max_notional: float = 0.20
    gross_cap: float = 1.2
    daily_loss_halt: float = 0.02
    dd_halve: float = 0.06
    dd_stop: float = 0.12
    max_positions: int = 10
    max_atr: float = 0.07
    min_price: float = 5.0
    cost_bps: float = 10.0
    hedge_cost_bps: float = 2.0
    hedge: bool = True


def mode_of(reg: dict, p: RegimeParams) -> str:
    """Legacy single-report rule (fixed yield levels). Prefer modes_for()."""
    rd, y = reg.get("rate_dir", 0), reg.get("y10")
    fade = (p.use_rate_dir and rd == 1) or (p.use_y10 and y is not None and y >= p.y10_hi)
    mom = (not p.use_rate_dir or rd <= 0) and (not p.use_y10 or (y is not None and y < p.y10_lo))
    return "FADE" if fade else "MOMENTUM" if mom else "NEUTRAL"


def modes_for(regs: dict, p: RegimeParams) -> dict:
    """{report_date: mode} using only reports up to each date; no fixed yield level unless regime_method='fixed'."""
    if p.regime_method == "fixed" and not p.use_y10:
        return {d: mode_of(r, p) for d, r in regs.items()}
    return {d: m for d, (m, sc) in context.regime_series(regs, p.regime_method, k=p.regime_k).items()}


def run(sections: dict[dt.date, list], texts: dict[dt.date, str], start: dt.date, end: dt.date,
        p: RegimeParams = RegimeParams(), equity0: float = 100_000.0, cache_dir: str = "data/prices"):
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end, cache_dir))
    td = sorted(d for d in spy if d <= end)
    D = {"SPY": spy}

    def dm(sym):
        if sym not in D:
            try:
                D[sym] = prices.daily_map(prices.get_bars(sym, "1d", start - dt.timedelta(days=45), end, cache_dir))
            except Exception:
                D[sym] = {}
        return D[sym]

    REG = {d: context.regime(texts[d]) for d in texts}
    MODE = modes_for(REG, p)
    SEC = {d: context.sector_stances(texts[d]) for d in texts}
    CAT = {d: context.catalysts(texts[d]) for d in texts}

    def listed_days(sym, R):
        k = 0
        for j in range(1, 40):
            pr = R - dt.timedelta(days=j)
            if pr in sections and sym in [map_play(q.name)[0] for q in sections[pr]]:
                k += 1
            else:
                break
        return k

    def signals_for(T):
        R, plays = plays_for_session(sections, T)
        if not plays:
            return [], "NONE", None
        mode = MODE[R]
        out = []
        p1 = plays[0]
        sym, rdir = map_play(p1.name)
        f = features(dataclasses.asdict(p1)) if sym else None
        if mode == "MOMENTUM":
            if p.mom_theme and sym and rdir:
                out.append(("MOM_THEME", sym, rdir, p.hold_theme, 1.0, p1.name))
            if p.mom_sector:
                for etf, sv in SEC[R].items():
                    if sv == 1:
                        out.append(("MOM_SECTOR", etf, 1, p.hold_sector, 0.5, "Bullish " + etf))
            if p.mom_cat:
                n = 0
                for tk, dd in CAT[R]:
                    if dd == 1 and n < p.max_cat_per_day:
                        out.append(("MOM_CAT", tk, 1, p.hold_cat, 0.5, "catalyst ↑ " + tk)); n += 1
        elif mode == "FADE":
            if p.fade_theme and sym and rdir and f and (f["fear_theme"] == 0 or not p.fade_greed_only):
                out.append(("FADE_THEME", sym, -rdir, p.hold_theme, 1.0, p1.name))
            if p.fade_new2 and len(plays) > 1:
                s2, r2 = map_play(plays[1].name)
                if s2 and r2 and listed_days(s2, R) == 0:
                    out.append(("FADE_NEW2", s2, -r2, p.hold_theme, 0.75, plays[1].name))
            if p.fade_long34:
                for q in plays[2:4]:
                    s3, r3 = map_play(q.name)
                    if s3 and r3 and listed_days(s3, R) >= 1:
                        out.append(("FADE_LONG34", s3, r3, p.hold_theme, 0.5, q.name))
            if p.fade_cat_down:
                n = 0
                for tk, dd in CAT[R]:
                    if dd == -1 and n < p.max_cat_per_day:
                        out.append(("FADE_CATDOWN", tk, 1, p.hold_cat, 0.5, "catalyst ↓ (contrarian long) " + tk)); n += 1
            if p.fade_sector:
                for etf, sv in SEC[R].items():
                    if sv == 1:
                        out.append(("FADE_SECTOR", etf, -1, p.hold_sector, 0.5, "Bullish " + etf))
        return out, mode, R

    equity, peak = equity0, equity0
    open_pos, closed, daily = [], [], []
    hedge_notional, halted_week = 0.0, None
    modes = {}
    i0 = next(k for k, d in enumerate(td) if d >= start)
    for i in range(i0, len(td)):
        T = td[i]
        if T not in spy or td[i - 1] not in spy:
            continue
        pnl_pos = 0.0
        dd = equity / peak - 1
        wk = T.isocalendar()[:2]
        blocked = (halted_week == wk) or (dd <= -p.dd_stop)
        size_mult = 0.5 if dd <= -p.dd_halve else 1.0
        sigs, mode, R = signals_for(T)
        modes[T.isoformat()] = mode
        held = {x["sym"] for x in open_pos}
        gross = sum(abs(x["qty"] * x["mark"]) for x in open_pos)
        for leg, sym, side, hold, scale, name in sigs:
            if blocked or sym in held or len(open_pos) >= p.max_positions:
                continue
            d = dm(sym)
            if T not in d or td[i - 1] not in d:
                continue
            atr = prices.atr_pct(d, T); o = d[T][0]
            if atr is None or atr > p.max_atr or o < p.min_price:
                continue
            notional = min(equity * p.risk_per_atr / atr, equity * p.max_notional) * scale * size_mult
            notional = min(notional, max(0.0, equity * p.gross_cap - gross))
            qty = int(notional / o)
            if qty <= 0:
                continue
            gross += qty * o
            # sector / catalyst legs are "vs SPY": add the offsetting SPY notional to the hedge book implicitly via net exposure
            open_pos.append(dict(leg=leg, sym=sym, side=side, entry=o, qty=qty, stop=o * (1 - side * p.stop_atr * atr), entry_day=T,
                                 exit_idx=i + hold - 1, report=R, play=name, atr=atr, mark=o, mode=mode))
            held.add(sym)
            pnl_pos -= qty * o * p.cost_bps / 2e4
        still = []
        for x in open_pos:
            d = dm(x["sym"])
            if T not in d:
                still.append(x); continue
            o, h, l, c, v = d[T][:5]
            prev_mark = x["mark"]; exit_px, why = None, None
            if (h >= x["stop"] if x["side"] == -1 else l <= x["stop"]):
                exit_px, why = x["stop"], "stop"
                if (x["side"] == -1 and o > x["stop"]) or (x["side"] == 1 and o < x["stop"]):
                    exit_px = o
            elif i >= x["exit_idx"]:
                exit_px, why = c, "time"
            mark = exit_px if exit_px is not None else c
            pnl_pos += (mark - prev_mark) * x["side"] * x["qty"]; x["mark"] = mark
            if exit_px is not None:
                pnl_pos -= x["qty"] * exit_px * p.cost_bps / 2e4
                closed.append({**{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in x.items()}, "exit": exit_px, "exit_day": T.isoformat(),
                               "exit_reason": why, "ret": (exit_px / x["entry"] - 1) * x["side"] - p.cost_bps / 1e4})
            else:
                still.append(x)
        open_pos = still
        spy_ret = spy[T][3] / spy[td[i - 1]][3] - 1
        if open_pos and (pnl_pos + (hedge_notional * spy_ret if p.hedge else 0.0)) <= -p.daily_loss_halt * equity:
            for x in open_pos:
                d = dm(x["sym"]); c = d[T][3] if T in d else x["mark"]
                pnl_pos += (c - x["mark"]) * x["side"] * x["qty"] - x["qty"] * c * p.cost_bps / 2e4
                closed.append({**{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in x.items()}, "exit": c, "exit_day": T.isoformat(),
                               "exit_reason": "halt", "ret": (c / x["entry"] - 1) * x["side"] - p.cost_bps / 1e4})
            open_pos = []; halted_week = wk
        pnl_h = 0.0
        if p.hedge:
            pnl_h = hedge_notional * spy_ret
            net = sum(x["side"] * x["qty"] * x["mark"] for x in open_pos)
            new_h = -net
            pnl_h -= abs(new_h - hedge_notional) * p.hedge_cost_bps / 1e4
            hedge_notional = new_h
        equity += pnl_pos + pnl_h; peak = max(peak, equity)
        daily.append((T.isoformat(), pnl_pos, pnl_h, equity, sum(x["side"] * x["qty"] * x["mark"] for x in open_pos) / equity, len(open_pos),
                      sum(abs(x["qty"] * x["mark"]) for x in open_pos) / equity, int(blocked)))
    return {"equity0": equity0, "equity": equity, "trades": closed, "daily": daily, "modes": modes, "params": dataclasses.asdict(p)}
