"""Event-level intraday backtest of the Retail Gap Fade strategy.

Execution model (conservative):
* entry at the session open print (+ slippage),
* stop / target evaluated on each intraday bar's high/low; if both are touched
  inside one bar the STOP is assumed to have been hit first,
* otherwise flat at the last bar before `exit_time` (close of the 15:30 bar for
  1h data, close of the 15:45 bar for 15m data), minus slippage,
* daily and weekly loss caps gate NEW entries only.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import statistics as st
from collections import defaultdict

from . import prices
from .mapping import map_play
from .strategy import Params, build_signal, plays_for_session, position_size


def simulate_trade(bars, sig, p: Params):
    """Return (exit_px, exit_reason, exit_time, mfe, mae) for one signal on the session bars."""
    slip = p.slippage_bps / 1e4
    side = sig.side
    best = worst = 0.0
    for i, (t, o, h, l, c, v) in enumerate(bars):
        if i == 0:
            # entry bar: only the part after the open counts; assume worst-case ordering
            pass
        fav = (h / sig.entry - 1) * side if side == 1 else (1 - l / sig.entry)
        adv = (1 - l / sig.entry) if side == 1 else (h / sig.entry - 1)
        best, worst = max(best, fav), max(worst, adv)
        hit_stop = l <= sig.stop if side == 1 else h >= sig.stop
        hit_tgt = h >= sig.target if side == 1 else l <= sig.target
        if hit_stop:
            return sig.stop * (1 - slip * side), "stop", t, best, worst
        if hit_tgt:
            return sig.target * (1 - slip * side), "target", t, best, worst
    last = bars[-1]
    return last[4] * (1 - slip * side), "time", last[0], best, worst


def run(sections: dict[dt.date, list], start: dt.date, end: dt.date, interval: str = "1h", p: Params = Params(),
        equity0: float = 100_000.0, cache_dir: str = "data/prices", ranks=(1, 2), verbose=False):
    spy_d = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end, cache_dir))
    spy_h = prices.get_bars("SPY", interval, start, end, cache_dir)
    tdays = sorted(d for d in spy_d if start <= d <= end)
    equity = equity0
    trades, daily_pnl, skipped = [], {}, []
    week_pnl = defaultdict(float)
    cache_h, cache_d = {}, {}
    for i, T in enumerate(tdays):
        rdate, plays = plays_for_session(sections, T)
        if not plays:
            continue
        prevT = tdays[i - 1] if i > 0 else None
        wk = T.isocalendar()[:2]
        day_pnl = 0.0
        n_today = 0
        sb_spy = prices.session_bars(spy_h, T)
        spy_gap = (sb_spy[0][1] / spy_d[prevT][3] - 1) if (sb_spy and prevT in spy_d) else None
        for play in plays:
            if play.rank not in ranks:
                continue
            sym, rdir = map_play(play.name)
            if sym is None or rdir == 0:
                continue
            if sym not in cache_h:
                try:
                    cache_h[sym] = prices.get_bars(sym, interval, start, end, cache_dir)
                    cache_d[sym] = prices.daily_map(prices.get_bars(sym, "1d", start - dt.timedelta(days=45), end, cache_dir))
                except Exception as e:
                    cache_h[sym], cache_d[sym] = [], {}
            bars = prices.session_bars(cache_h[sym], T)
            if len(bars) < 4 or prevT not in cache_d[sym]:
                continue
            atr = prices.atr_pct(cache_d[sym], T)
            sig = build_signal(T, rdate, play.rank, play.name, sym, rdir, cache_d[sym][prevT][3], bars[0][1], atr, spy_gap, p)
            if sig.side == 0:
                skipped.append(sig.to_dict()); continue
            if n_today >= p.max_trades_per_day or day_pnl <= -p.daily_loss_cap * equity or week_pnl[wk] <= -p.weekly_loss_cap * equity:
                sig.reason += " | blocked by risk cap"; skipped.append(sig.to_dict()); continue
            qty = position_size(equity, sig.entry, sig.stop, p)
            if qty <= 0:
                continue
            exit_px, why, when, mfe, mae = simulate_trade(bars, sig, p)
            pnl = (exit_px - sig.entry) * sig.side * qty
            ret = (exit_px / sig.entry - 1) * sig.side
            trades.append({**sig.to_dict(), "qty": qty, "exit": exit_px, "exit_reason": why, "exit_time": when.isoformat(),
                           "ret": ret, "pnl": pnl, "mfe": mfe, "mae": mae, "equity_before": equity})
            equity += pnl; day_pnl += pnl; week_pnl[wk] += pnl; n_today += 1
        if day_pnl:
            daily_pnl[T.isoformat()] = day_pnl
    return {"equity0": equity0, "equity": equity, "trades": trades, "daily_pnl": daily_pnl, "skipped": skipped, "params": p.__dict__ | {"entry_time": str(p.entry_time), "exit_time": str(p.exit_time)}, "interval": interval}


def summarize(res: dict) -> dict:
    tr = res["trades"]
    if not tr:
        return {"n": 0}
    rets = [t["ret"] for t in tr]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    dp = list(res["daily_pnl"].values())
    eq = res["equity0"]; peak = eq; mdd = 0.0
    for v in dp:
        eq += v; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    mean = st.mean(rets); sd = st.pstdev(rets) if len(rets) > 1 else 0
    daily_ret = [v / res["equity0"] for v in dp]
    sharpe = (st.mean(daily_ret) / st.pstdev(daily_ret) * math.sqrt(252)) if len(daily_ret) > 2 and st.pstdev(daily_ret) > 0 else float("nan")
    by_reason = defaultdict(int)
    for t in tr:
        by_reason[t["exit_reason"]] += 1
    return {
        "n": len(tr), "hit": len(wins) / len(tr), "avg_ret_bp": mean * 1e4, "median_ret_bp": st.median(rets) * 1e4,
        "avg_win_bp": (st.mean(wins) * 1e4) if wins else 0, "avg_loss_bp": (st.mean(losses) * 1e4) if losses else 0,
        "t_stat": (mean / (sd / math.sqrt(len(rets)))) if sd else 0, "profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else float("inf"),
        "total_return": res["equity"] / res["equity0"] - 1, "max_drawdown": mdd, "sharpe_daily": sharpe,
        "trading_days": len(dp), "exits": dict(by_reason),
    }
