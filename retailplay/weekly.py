"""Retail #1 Fade (weekly) - the opposite of "continuation".

Finding on the archive (2026-06-25 .. 2026-09-30): the #1 "What Retail Is Playing"
theme UNDER-performs over the following week, while the #2 theme does not.
So the weekly strategy is a pair: short the #1 theme (in the direction opposite to
retail), hedged with an equal-notional long in either SPY or the #2 theme,
held for `hold` sessions, with an ATR stop on the short leg.

Point-in-time: entry at the open of the first session after the newest report;
one entry per calendar week (first session of the ISO week) by default, or a
rolling schedule every `hold` sessions at a given phase for robustness checks.
"""
from __future__ import annotations
import dataclasses
import datetime as dt
import math
import statistics as st
from collections import defaultdict

from . import prices
from .mapping import map_play
from .strategy import plays_for_session


@dataclasses.dataclass(frozen=True)
class WeeklyParams:
    hold: int = 5                 # sessions held (entry day counts as 1)
    hedge: str = "spy"            # 'spy' | 'rank2' | 'none'
    stop_atr: float = 1.5         # stop on the short leg, ATR10 units, daily high/low
    risk_per_trade: float = 0.01  # equity at risk at the stop (short leg)
    max_notional: float = 0.5     # cap per leg as fraction of equity
    max_atr: float = 0.06
    min_price: float = 5.0
    cost_bps: float = 10.0        # round trip per leg
    schedule: str = "weekly"      # 'weekly' (first session of ISO week) | 'rolling'
    phase: int = 0                # for 'rolling': entry sessions i with i % hold == phase
    exclude: tuple = ()           # symbols never traded (robustness checks)


def run(sections: dict[dt.date, list], start: dt.date, end: dt.date, p: WeeklyParams = WeeklyParams(),
        equity0: float = 100_000.0, cache_dir: str = "data/prices"):
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

    equity = equity0
    trades = []
    i0 = next(k for k, d in enumerate(td) if d >= start)
    busy_until = -1
    for i in range(i0, len(td)):
        T = td[i]
        if i + p.hold - 1 >= len(td):
            break
        if p.schedule == "weekly":
            if i > 0 and td[i - 1].isocalendar()[1] == T.isocalendar()[1]:
                continue
        else:
            if i % p.hold != p.phase:
                continue
        if i <= busy_until:
            continue
        rdate, plays = plays_for_session(sections, T)
        if not plays:
            continue
        p1 = plays[0]
        sym, rdir = map_play(p1.name)
        if sym is None or rdir == 0 or sym in p.exclude:
            continue
        d = dm(sym)
        if T not in d or td[i - 1] not in d:
            continue
        atr = prices.atr_pct(d, T)
        if atr is None or atr > p.max_atr or d[T][0] < p.min_price:
            continue
        side = -rdir                      # fade the crowd
        entry = d[T][0]
        stop = entry * (1 - side * p.stop_atr * atr)
        notional = min(equity * p.risk_per_trade / (p.stop_atr * atr), equity * p.max_notional)
        qty = int(notional / entry)
        if qty <= 0:
            continue
        # hedge leg
        hsym, hside = None, 0
        if p.hedge == "spy":
            hsym, hside = "SPY", 1
        elif p.hedge == "rank2" and len(plays) > 1:
            s2, r2 = map_play(plays[1].name)
            if s2 and r2 and s2 != sym and s2 not in p.exclude:
                hsym, hside = s2, r2
        hd = dm(hsym) if hsym else {}
        if hsym and (T not in hd):
            hsym = None
        hqty = int(qty * entry / hd[T][0]) if hsym else 0
        hentry = hd[T][0] if hsym else 0.0
        # walk the holding window
        exit_px, why, exit_day = None, "time", td[i + p.hold - 1]
        for k in range(i, i + p.hold):
            day = td[k]
            if day not in d:
                continue
            o, h, l, c, v = d[day][:5]
            if (h >= stop if side == -1 else l <= stop):
                exit_px, why, exit_day = stop, "stop", day
                break
        if exit_px is None:
            exit_px = d[exit_day][3] if exit_day in d else d[max(x for x in d if x <= exit_day)][3]
        cost = p.cost_bps / 1e4
        ret1 = (exit_px / entry - 1) * side - cost
        pnl = ret1 * qty * entry
        reth = 0.0
        if hsym:
            hx = hd[exit_day][3] if exit_day in hd else hd[max(x for x in hd if x <= exit_day)][3]
            reth = (hx / hentry - 1) * hside - cost
            pnl += reth * hqty * hentry
        trades.append(dict(report=rdate.isoformat(), entry_day=T.isoformat(), exit_day=exit_day.isoformat(), play=p1.name, symbol=sym,
                           side=side, entry=entry, stop=stop, exit=exit_px, exit_reason=why, qty=qty, ret_short_leg=ret1,
                           hedge=hsym, hedge_side=hside, hedge_qty=hqty, ret_hedge_leg=reth, pnl=pnl, ret_total=pnl / equity, equity_before=equity))
        equity += pnl
        busy_until = i + p.hold - 1
    return {"equity0": equity0, "equity": equity, "trades": trades, "params": dataclasses.asdict(p)}


def summarize(res):
    tr = res["trades"]
    if not tr:
        return {"n": 0}
    r = [t["ret_total"] for t in tr]
    s = [t["ret_short_leg"] for t in tr]
    eq = res["equity0"]; peak = eq; mdd = 0.0
    for t in tr:
        eq += t["pnl"]; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    m = st.mean(r); sd = st.pstdev(r)
    ms = st.mean(s); sds = st.pstdev(s)
    return {"n": len(tr), "hit": sum(x > 0 for x in r) / len(r), "avg_ret_pct": m * 100, "t": (m / (sd / math.sqrt(len(r)))) if sd else 0,
            "short_leg_avg_pct": ms * 100, "short_leg_hit": sum(x > 0 for x in s) / len(s), "short_leg_t": (ms / (sds / math.sqrt(len(s)))) if sds else 0,
            "total_return": res["equity"] / res["equity0"] - 1, "max_drawdown": mdd, "stops": sum(t["exit_reason"] == "stop" for t in tr),
            "sharpe_weekly": (m / sd * math.sqrt(52)) if sd else float("nan")}
