"""Narrative Rotation book: a multi-leg, hedged, 5-session-hold portfolio driven by the
"What Retail Is Playing" section plus text sentiment.

Legs (each can be toggled):
  S1   short the #1 theme when it is a GREED narrative (AI / crypto / squeeze / rotation),
       optionally only when the author's crowding language is strong (warn >= warn_min).
       Fear narratives (gold, oil, defence, bonds) are never faded.
  LP   long the persisting lower-rank themes (#2..#4 that were already listed yesterday),
       in retail's direction.
  DR   short a GREED theme that just dropped out of the list (from any rank).
  HEDGE SPY position sized daily to the book's net dollar exposure (sign-flipped).

Execution: entries at the next open after the report; 1.5 ATR10 stop on daily high/low;
time exit at the close of the `hold`-th session; `cost_bps` round trip per position;
one open position per symbol; equal notional per position.
"""
from __future__ import annotations
import dataclasses
import datetime as dt
import math
import statistics as st
from collections import defaultdict

from . import prices
from .mapping import map_play
from .sentiment import features


@dataclasses.dataclass(frozen=True)
class BookParams:
    hold: int = 5
    leg_s1: bool = True
    leg_lp: bool = True
    leg_dr: bool = True
    hedge: bool = True
    warn_min: float = 0.0        # S1 only when warn >= this (0 = no filter)
    lp_ranks: tuple = (2, 3, 4)
    lp_min_k: int = 1            # persistence (days already listed) required for LP
    lp_theme: str = "any"        # 'any' | 'greed' | 'fear'
    dr_greed_only: bool = True
    stop_atr: float = 1.5
    notional: float = 0.10       # per position, fraction of equity at entry (size_mode='notional')
    size_mode: str = "notional"  # 'notional' | 'vol'  (vol: notional = equity * risk_per_atr / ATR10, capped)
    risk_per_atr: float = 0.004  # vol sizing: one ATR move in the position = 0.4% of equity
    max_notional: float = 0.25   # cap per position, fraction of equity
    s1_fear_scale: float = 0.5   # size multiplier for a FEAR #1 (0 = never fade fear themes)
    gross_cap: float = 1.0       # max sum |notional| of theme positions (ex hedge)
    daily_loss_halt: float = 0.015  # close everything and stop new entries for the rest of the ISO week
    dd_halve: float = 0.06       # size halved while drawdown from peak exceeds this
    dd_stop: float = 0.10        # no new entries while drawdown exceeds this
    max_positions: int = 8
    max_atr: float = 0.06
    min_price: float = 5.0
    cost_bps: float = 10.0
    hedge_cost_bps: float = 2.0


def run(sections: dict[dt.date, list], start: dt.date, end: dt.date, p: BookParams = BookParams(),
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

    rdates = sorted(sections)

    def signals_for(T: dt.date):
        cands = [d for d in rdates if d < T]
        if not cands:
            return []
        R = max(cands)
        plays = sections[R]
        out = []
        syms_today = [map_play(q.name)[0] for q in plays]

        def listed_days(sym, R):
            k = 0
            for j in range(1, 40):
                pr = R - dt.timedelta(days=j)
                if pr in sections and sym in [map_play(q.name)[0] for q in sections[pr]]:
                    k += 1
                else:
                    break
            return k
        for q in plays:
            sym, rdir = map_play(q.name)
            if not sym or not rdir:
                continue
            f = features(dataclasses.asdict(q))
            if q.rank == 1 and p.leg_s1 and f["warn"] >= p.warn_min:
                scale = 1.0 if f["fear_theme"] == 0 else p.s1_fear_scale
                if scale > 0:
                    out.append(("S1", sym, -rdir, R, q.name, scale))
            if q.rank in p.lp_ranks and p.leg_lp and listed_days(sym, R) >= p.lp_min_k and (p.lp_theme == "any" or (p.lp_theme == "fear") == (f["fear_theme"] == 1)):
                out.append(("LP", sym, rdir, R, q.name, 1.0))
        if p.leg_dr:
            prev = R - dt.timedelta(days=1)
            if prev in sections:
                for q in sections[prev]:
                    sym, rdir = map_play(q.name)
                    if not sym or not rdir or sym in syms_today:
                        continue
                    f = features(dataclasses.asdict(q))
                    if p.dr_greed_only and f["fear_theme"] == 1:
                        continue
                    out.append(("DR", sym, -rdir, R, q.name, 1.0))
        return out

    equity = equity0
    peak = equity0
    open_pos = []          # dicts
    closed = []
    daily = []             # (date, pnl_positions, pnl_hedge, equity, net_exposure, n_pos, gross, halted)
    hedge_notional = 0.0   # signed $ in SPY held from previous close
    halted_week = None     # ISO week during which new entries are blocked after a daily-loss halt
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
        # 1) entries at today's open
        held = {x["sym"] for x in open_pos}
        gross = sum(abs(x["qty"] * x["mark"]) for x in open_pos if "mark" in x)
        for leg, sym, side, R, name, scale in signals_for(T):
            if blocked or sym in held or len(open_pos) >= p.max_positions:
                continue
            d = dm(sym)
            if T not in d or td[i - 1] not in d:
                continue
            atr = prices.atr_pct(d, T)
            o = d[T][0]
            if atr is None or atr > p.max_atr or o < p.min_price:
                continue
            if p.size_mode == "vol":
                notional = min(equity * p.risk_per_atr / atr, equity * p.max_notional)
            else:
                notional = equity * p.notional
            notional *= scale * size_mult
            notional = min(notional, max(0.0, equity * p.gross_cap - gross))
            qty = int(notional / o)
            if qty <= 0:
                continue
            gross += qty * o
            open_pos.append(dict(leg=leg, sym=sym, side=side, entry=o, qty=qty, stop=o * (1 - side * p.stop_atr * atr),
                                 entry_day=T, exit_idx=i + p.hold - 1, report=R, play=name, atr=atr, mark=o))
            held.add(sym)
            pnl_pos -= qty * o * p.cost_bps / 2e4
        # 2) mark / stop / exit positions through today
        still = []
        for x in open_pos:
            d = dm(x["sym"])
            if T not in d:
                still.append(x); continue
            o, h, l, c, v = d[T][:5]
            prev_mark = x.get("mark", x["entry"])
            exit_px, why = None, None
            if (h >= x["stop"] if x["side"] == -1 else l <= x["stop"]):
                exit_px, why = x["stop"], "stop"
                # gap through the stop: fill at the open if worse
                if (x["side"] == -1 and o > x["stop"]) or (x["side"] == 1 and o < x["stop"]):
                    exit_px = o
            elif i >= x["exit_idx"]:
                exit_px, why = c, "time"
            mark = exit_px if exit_px is not None else c
            pnl_pos += (mark - prev_mark) * x["side"] * x["qty"]
            x["mark"] = mark
            if exit_px is not None:
                pnl_pos -= x["qty"] * exit_px * p.cost_bps / 2e4
                ret = (exit_px / x["entry"] - 1) * x["side"] - p.cost_bps / 1e4
                closed.append({**{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in x.items()}, "exit": exit_px, "exit_day": T.isoformat(), "exit_reason": why, "ret": ret})
            else:
                still.append(x)
        open_pos = still
        # 2b) portfolio daily-loss halt: liquidate at today's close, block new entries for the rest of the week
        if open_pos and (pnl_pos + (hedge_notional * (spy[T][3] / spy[td[i - 1]][3] - 1) if p.hedge else 0.0)) <= -p.daily_loss_halt * equity:
            for x in open_pos:
                d = dm(x["sym"])
                c = d[T][3] if T in d else x["mark"]
                pnl_pos += (c - x["mark"]) * x["side"] * x["qty"] - x["qty"] * c * p.cost_bps / 2e4
                ret = (c / x["entry"] - 1) * x["side"] - p.cost_bps / 1e4
                closed.append({**{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in x.items()}, "exit": c, "exit_day": T.isoformat(), "exit_reason": "halt", "ret": ret})
            open_pos = []
            halted_week = wk
        # 3) hedge: pnl on yesterday's hedge notional with SPY close-to-close, then resize to today's net exposure
        pnl_h = 0.0
        if p.hedge:
            spy_ret = spy[T][3] / spy[td[i - 1]][3] - 1
            pnl_h = hedge_notional * spy_ret
            net = sum(x["side"] * x["qty"] * x["mark"] for x in open_pos)
            new_h = -net
            pnl_h -= abs(new_h - hedge_notional) * p.hedge_cost_bps / 1e4
            hedge_notional = new_h
        equity += pnl_pos + pnl_h
        peak = max(peak, equity)
        daily.append((T.isoformat(), pnl_pos, pnl_h, equity, sum(x["side"] * x["qty"] * x["mark"] for x in open_pos) / equity, len(open_pos),
                      sum(abs(x["qty"] * x["mark"]) for x in open_pos) / equity, int(blocked)))
    return {"equity0": equity0, "equity": equity, "trades": closed, "daily": daily, "params": dataclasses.asdict(p)}


def summarize(res, split: str | None = None):
    tr = res["trades"]; dl = res["daily"]
    out = {"n": len(tr)}
    if not tr:
        return out
    by = defaultdict(list)
    for t in tr:
        by[t["leg"]].append(t["ret"])
    for leg, v in by.items():
        m = st.mean(v); sd = st.pstdev(v)
        out[f"{leg}_n"] = len(v); out[f"{leg}_avg_bp"] = m * 1e4; out[f"{leg}_hit"] = sum(x > 0 for x in v) / len(v); out[f"{leg}_t"] = (m / (sd / math.sqrt(len(v)))) if sd and len(v) > 1 else 0
    rets = [(d[1] + d[2]) / (d[3] - d[1] - d[2]) for d in dl]
    eq = res["equity0"]; peak = eq; mdd = 0
    for d in dl:
        eq = d[3]; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    out.update(total_return=res["equity"] / res["equity0"] - 1, max_drawdown=mdd,
               sharpe=(st.mean(rets) / st.pstdev(rets) * math.sqrt(252)) if len(rets) > 2 and st.pstdev(rets) > 0 else float("nan"),
               avg_gross=st.mean(abs(d[4]) for d in dl), avg_positions=st.mean(d[5] for d in dl), days=len(dl),
               stops=sum(t["exit_reason"] == "stop" for t in tr))
    if split:
        for lbl, f in [("H1", lambda d: d[0] < split), ("H2", lambda d: d[0] >= split)]:
            sub = [d for d in dl if f(d)]
            if sub:
                r = [(d[1] + d[2]) / (d[3] - d[1] - d[2]) for d in sub]
                out[f"{lbl}_return"] = math.prod(1 + x for x in r) - 1
                out[f"{lbl}_sharpe"] = (st.mean(r) / st.pstdev(r) * math.sqrt(252)) if st.pstdev(r) > 0 else float("nan")
    return out


def risk_report(res, spy_daily: dict | None = None, split: str | None = None) -> dict:
    """Full risk statistics from the daily series (returns on prior equity)."""
    dl = res["daily"]
    if len(dl) < 5:
        return {"days": len(dl)}
    rets = [(d[1] + d[2]) / (d[3] - d[1] - d[2]) for d in dl]
    dates = [d[0] for d in dl]
    n = len(rets)
    mean, sd = st.mean(rets), st.pstdev(rets)
    downside = [min(r, 0) for r in rets]
    dsd = math.sqrt(st.mean([x * x for x in downside]))
    eq, peak, mdd, dd_len, cur_len, ddstart = res["equity0"], res["equity0"], 0.0, 0, 0, None
    for d in dl:
        eq = d[3]
        if eq >= peak:
            peak = eq; cur_len = 0
        else:
            cur_len += 1; dd_len = max(dd_len, cur_len)
        mdd = min(mdd, eq / peak - 1)
    srt = sorted(rets)
    var95, var99 = srt[int(0.05 * n)], srt[max(int(0.01 * n), 0)]
    cvar95 = st.mean(srt[: max(int(0.05 * n), 1)])
    # weekly aggregation
    wk = defaultdict(float)
    for d, r in zip(dates, rets):
        y, w, _ = dt.date.fromisoformat(d).isocalendar(); wk[(y, w)] += r
    wr = list(wk.values())
    out = {
        "days": n, "weeks": len(wr), "total_return": res["equity"] / res["equity0"] - 1,
        "ann_return": (1 + mean) ** 252 - 1, "ann_vol": sd * math.sqrt(252),
        "sharpe": (mean / sd * math.sqrt(252)) if sd else float("nan"),
        "sortino": (mean / dsd * math.sqrt(252)) if dsd else float("nan"),
        "max_drawdown": mdd, "calmar": (((1 + mean) ** 252 - 1) / -mdd) if mdd < 0 else float("nan"),
        "longest_dd_days": dd_len, "worst_day": min(rets), "best_day": max(rets),
        "worst_week": min(wr), "best_week": max(wr), "weekly_hit": sum(x > 0 for x in wr) / len(wr),
        "daily_hit": sum(x > 0 for x in rets) / sum(1 for x in rets if x != 0) if any(rets) else 0,
        "var95_daily": var95, "var99_daily": var99, "cvar95_daily": cvar95,
        "skew": (st.mean([((r - mean) / sd) ** 3 for r in rets]) if sd else 0),
        "avg_gross": st.mean(d[6] for d in dl), "max_gross": max(d[6] for d in dl),
        "avg_net": st.mean(d[4] for d in dl), "max_abs_net": max(abs(d[4]) for d in dl),
        "avg_positions": st.mean(d[5] for d in dl), "days_blocked": sum(d[7] for d in dl),
        "pct_days_in_market": sum(1 for d in dl if d[5] > 0) / n,
    }
    tr = res["trades"]
    out["trades"] = len(tr); out["stops"] = sum(t["exit_reason"] == "stop" for t in tr); out["halts"] = sum(t["exit_reason"] == "halt" for t in tr)
    by = defaultdict(list)
    for t in tr:
        by[t["leg"]].append(t)
    for leg, v in by.items():
        r = [t["ret"] for t in v]
        pnl = sum((t["exit"] / t["entry"] - 1) * t["side"] * t["qty"] * t["entry"] for t in v)
        out[f"leg_{leg}"] = {"n": len(v), "avg_bp": st.mean(r) * 1e4, "hit": sum(x > 0 for x in r) / len(r),
                             "t": (st.mean(r) / (st.pstdev(r) / math.sqrt(len(r)))) if len(r) > 1 and st.pstdev(r) else 0,
                             "pnl_pct_of_equity0": pnl / res["equity0"], "stops": sum(t["exit_reason"] == "stop" for t in v)}
    hp = sum(d[2] for d in dl); out["hedge_pnl_pct"] = hp / res["equity0"]
    if spy_daily:
        sr = []
        prev = None
        for d in dates:
            dd_ = dt.date.fromisoformat(d)
            if prev is not None and dd_ in spy_daily and prev in spy_daily:
                sr.append(spy_daily[dd_][3] / spy_daily[prev][3] - 1)
            else:
                sr.append(0.0)
            prev = dd_
        ms, ss = st.mean(sr), st.pstdev(sr)
        cov = st.mean([(a - mean) * (b - ms) for a, b in zip(rets, sr)])
        out["beta_spy"] = cov / (ss * ss) if ss else 0; out["corr_spy"] = cov / (sd * ss) if sd and ss else 0
        out["spy_total_return_same_period"] = math.prod(1 + x for x in sr) - 1
    if split:
        for lbl, f in [("H1", lambda d: d < split), ("H2", lambda d: d >= split)]:
            r = [x for d, x in zip(dates, rets) if f(d)]
            if len(r) > 2:
                out[f"{lbl}_return"] = math.prod(1 + x for x in r) - 1
                out[f"{lbl}_sharpe"] = (st.mean(r) / st.pstdev(r) * math.sqrt(252)) if st.pstdev(r) else float("nan")
    return out
