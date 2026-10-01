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
    notional: float = 0.10       # per position, fraction of equity at entry
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
            if q.rank == 1 and p.leg_s1 and f["fear_theme"] == 0 and f["warn"] >= p.warn_min:
                out.append(("S1", sym, -rdir, R, q.name))
            if q.rank in p.lp_ranks and p.leg_lp and listed_days(sym, R) >= p.lp_min_k and (p.lp_theme == "any" or (p.lp_theme == "fear") == (f["fear_theme"] == 1)):
                out.append(("LP", sym, rdir, R, q.name))
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
                    out.append(("DR", sym, -rdir, R, q.name))
        return out

    equity = equity0
    open_pos = []          # dicts
    closed = []
    daily = []             # (date, pnl_positions, pnl_hedge, equity, net_exposure)
    hedge_notional = 0.0   # signed $ in SPY held from previous close
    i0 = next(k for k, d in enumerate(td) if d >= start)
    for i in range(i0, len(td)):
        T = td[i]
        if T not in spy or td[i - 1] not in spy:
            continue
        pnl_pos = 0.0
        # 1) entries at today's open
        held = {x["sym"] for x in open_pos}
        for leg, sym, side, R, name in signals_for(T):
            if sym in held or len(open_pos) >= p.max_positions:
                continue
            d = dm(sym)
            if T not in d or td[i - 1] not in d:
                continue
            atr = prices.atr_pct(d, T)
            o = d[T][0]
            if atr is None or atr > p.max_atr or o < p.min_price:
                continue
            qty = int(equity * p.notional / o)
            if qty <= 0:
                continue
            open_pos.append(dict(leg=leg, sym=sym, side=side, entry=o, qty=qty, stop=o * (1 - side * p.stop_atr * atr),
                                 entry_day=T, exit_idx=i + p.hold - 1, report=R, play=name, atr=atr))
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
        daily.append((T.isoformat(), pnl_pos, pnl_h, equity, sum(x["side"] * x["qty"] * x["mark"] for x in open_pos) / equity, len(open_pos)))
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
