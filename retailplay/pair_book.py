"""Regime-switched PAIR book: every position is a long/short pair built from the same report.

Pairs by regime (regime = text vote, see context.regime_series):
  FADE (tightening):
    P_F1  long persisting #3/#4 theme   / short #1 theme          hold_f1 sessions
    P_F2  long ↓-catalyst (contrarian)  / short #1 theme          hold_f2
  MOMENTUM (easing):
    P_M1  long #1 theme                 / short Bearish-sector basket (Mixed if no Bearish)  hold_m1
    P_M2  long Bullish sector           / short Bearish-sector basket                        hold_m2
    P_M3  long ↑-catalyst               / short Bearish-sector basket                        hold_m3
  NEUTRAL: no new pairs.

Legs are vol-matched: each leg's notional = equity * risk_per_atr / ATR10 (capped), so both
legs carry the same ATR-dollar risk; a basket short splits that notional across its members.
Pair stop: close both legs when the pair's mark-to-market loss exceeds stop_mult x the pair
risk unit (long notional x ATR). Time exit at the hold horizon. Portfolio rules: gross cap,
max pairs, daily halt, drawdown de-risk; optional SPY hedge of the residual net.
"""
from __future__ import annotations
import dataclasses
import datetime as dt

from . import prices, context
from .mapping import map_play
from .strategy import plays_for_session


@dataclasses.dataclass(frozen=True)
class PairParams:
    regime_method: str = "text"
    regime_k: int = 10
    pf1: bool = True
    pf2: bool = True
    pm1: bool = True
    pm2: bool = True
    pm3: bool = True
    hold_f1: int = 10
    hold_f2: int = 20
    hold_m1: int = 10
    hold_m2: int = 10
    hold_m3: int = 20
    max_cat: int = 2
    max_basket: int = 3            # sectors in the short basket
    risk_per_atr: float = 0.004    # per leg: one ATR move = 0.4% of equity
    max_notional: float = 0.20     # per leg
    stop_mult: float = 2.5         # pair stop in risk units
    gross_cap: float = 1.5
    max_pairs: int = 6
    daily_loss_halt: float = 0.02
    dd_halve: float = 0.06
    dd_stop: float = 0.12
    max_atr: float = 0.07
    min_price: float = 5.0
    cost_bps: float = 10.0
    hedge_residual: bool = True
    hedge_cost_bps: float = 2.0


def run(sections, texts, start, end, p: PairParams = PairParams(), equity0=100_000.0, cache_dir="data/prices"):
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
    MODE = {d: m for d, (m, sc) in context.regime_series(REG, p.regime_method, k=p.regime_k).items()}
    SEC = {d: context.sector_stances(texts[d]) for d in texts}
    CAT = {d: context.catalysts(texts[d]) for d in texts}

    def listed(sym, R):
        pr = R - dt.timedelta(days=1)
        while pr not in sections and (R - pr).days < 4:
            pr -= dt.timedelta(days=1)
        return pr in sections and sym in [map_play(q.name)[0] for q in sections[pr]]

    def pair_candidates(T):
        R, plays = plays_for_session(sections, T)
        if not plays:
            return [], "NONE", None
        mode = MODE[R]
        out = []
        s1, d1 = map_play(plays[0].name)
        theme1 = s1 if (s1 and d1 == 1) else None
        pers34 = [map_play(q.name)[0] for q in plays[2:4] if map_play(q.name)[0] and map_play(q.name)[1] == 1 and listed(map_play(q.name)[0], R)]
        cat_dn = [t for t, dd in CAT[R] if dd == -1][: p.max_cat]
        cat_up = [t for t, dd in CAT[R] if dd == 1][: p.max_cat]
        bear = [e for e, v in SEC[R].items() if v == -1][: p.max_basket] or [e for e, v in SEC[R].items() if v == 0][: p.max_basket]
        bull = [e for e, v in SEC[R].items() if v == 1]
        if mode == "FADE" and theme1:
            if p.pf1:
                for s in pers34:
                    out.append(("P_F1", [s], [theme1], p.hold_f1, f"long {s} (persisting #3/#4) / short {theme1} (#1)"))
            if p.pf2:
                for t in cat_dn:
                    out.append(("P_F2", [t], [theme1], p.hold_f2, f"long {t} (↓ catalyst) / short {theme1} (#1)"))
        elif mode == "MOMENTUM" and bear:
            if p.pm1 and theme1:
                out.append(("P_M1", [theme1], bear, p.hold_m1, f"long {theme1} (#1) / short {'+'.join(bear)}"))
            if p.pm2:
                for e in bull:
                    out.append(("P_M2", [e], bear, p.hold_m2, f"long {e} (Bullish) / short {'+'.join(bear)}"))
            if p.pm3:
                for t in cat_up:
                    out.append(("P_M3", [t], bear, p.hold_m3, f"long {t} (↑ catalyst) / short {'+'.join(bear)}"))
        return out, mode, R

    equity, peak = equity0, equity0
    pairs, closed, daily = [], [], []
    hedge_notional, halted_week = 0.0, None
    modes = {}
    i0 = next(k for k, d in enumerate(td) if d >= start)
    for i in range(i0, len(td)):
        T = td[i]
        if T not in spy or td[i - 1] not in spy:
            continue
        pnl = 0.0
        dd = equity / peak - 1
        wk = T.isocalendar()[:2]
        blocked = (halted_week == wk) or (dd <= -p.dd_stop)
        size_mult = 0.5 if dd <= -p.dd_halve else 1.0
        cands, mode, R = pair_candidates(T)
        modes[T.isoformat()] = mode
        held = {leg["sym"] for pr in pairs for leg in pr["legs"] if leg["side"] == 1}  # no duplicate longs
        gross = sum(abs(l["qty"] * l["mark"]) for pr in pairs for l in pr["legs"])
        for kind, longs, shorts, hold, label in cands:
            if blocked or len(pairs) >= p.max_pairs or any(s in held for s in longs):
                continue
            legs = []
            ok = True
            for syms, side in ((longs, 1), (shorts, -1)):
                for s in syms:
                    d = dm(s)
                    if T not in d or td[i - 1] not in d:
                        ok = False; break
                    atr = prices.atr_pct(d, T); o = d[T][0]
                    if atr is None or atr > p.max_atr or o < p.min_price:
                        ok = False; break
                    notional = min(equity * p.risk_per_atr / atr, equity * p.max_notional) * size_mult / len(syms)
                    qty = int(notional / o)
                    if qty <= 0:
                        ok = False; break
                    legs.append(dict(sym=s, side=side, entry=o, qty=qty, atr=atr, mark=o))
                if not ok:
                    break
            if not ok:
                continue
            pg = sum(l["qty"] * l["entry"] for l in legs)
            if gross + pg > equity * p.gross_cap:
                continue
            gross += pg
            risk_unit = sum(l["qty"] * l["entry"] * l["atr"] for l in legs if l["side"] == 1)
            pairs.append(dict(kind=kind, legs=legs, entry_day=T, exit_idx=i + hold - 1, report=R, label=label, risk_unit=risk_unit, mode=mode, pnl=0.0))
            for l in legs:
                if l["side"] == 1:
                    held.add(l["sym"])
            pnl -= pg * p.cost_bps / 2e4
        still = []
        for pr in pairs:
            day_pnl = 0.0
            for l in pr["legs"]:
                d = dm(l["sym"])
                if T in d:
                    c = d[T][3]; day_pnl += (c - l["mark"]) * l["side"] * l["qty"]; l["mark"] = c
            pr["pnl"] += day_pnl; pnl += day_pnl
            why = None
            if pr["pnl"] <= -p.stop_mult * pr["risk_unit"]:
                why = "stop"
            elif i >= pr["exit_idx"]:
                why = "time"
            if why:
                pg = sum(l["qty"] * l["mark"] for l in pr["legs"]); pnl -= pg * p.cost_bps / 2e4
                closed.append({**{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in pr.items() if k != "legs"},
                               "legs": [{**l} for l in pr["legs"]], "exit_day": T.isoformat(), "exit_reason": why,
                               "ret": (pr["pnl"] - pg * p.cost_bps / 2e4) / sum(l["qty"] * l["entry"] for l in pr["legs"] if l["side"] == 1)})
            else:
                still.append(pr)
        pairs = still
        spy_ret = spy[T][3] / spy[td[i - 1]][3] - 1
        if pairs and (pnl + (hedge_notional * spy_ret if p.hedge_residual else 0.0)) <= -p.daily_loss_halt * equity:
            for pr in pairs:
                pg = sum(l["qty"] * l["mark"] for l in pr["legs"]); pnl -= pg * p.cost_bps / 2e4
                closed.append({**{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in pr.items() if k != "legs"}, "legs": [{**l} for l in pr["legs"]],
                               "exit_day": T.isoformat(), "exit_reason": "halt", "ret": pr["pnl"] / sum(l["qty"] * l["entry"] for l in pr["legs"] if l["side"] == 1)})
            pairs = []; halted_week = wk
        pnl_h = 0.0
        net = sum(l["side"] * l["qty"] * l["mark"] for pr in pairs for l in pr["legs"])
        if p.hedge_residual:
            pnl_h = hedge_notional * spy_ret
            new_h = -net; pnl_h -= abs(new_h - hedge_notional) * p.hedge_cost_bps / 1e4; hedge_notional = new_h
        equity += pnl + pnl_h; peak = max(peak, equity)
        daily.append((T.isoformat(), pnl, pnl_h, equity, net / equity, len(pairs), sum(abs(l["qty"] * l["mark"]) for pr in pairs for l in pr["legs"]) / equity, int(blocked)))
    # flatten for risk_report compatibility: 'leg' = pair kind, per-pair ret, sym = long leg
    trades = [{"leg": c["kind"], "sym": "/".join(l["sym"] for l in c["legs"]), "side": 1, "qty": 1, "entry": 1.0, "exit": 1.0 + c["ret"], "stop": 0.0,
               "exit_reason": c["exit_reason"], "ret": c["ret"], "entry_day": c["entry_day"], "exit_day": c["exit_day"], "play": c["label"], "pnl": c["pnl"], "mode": c["mode"]} for c in closed]
    return {"equity0": equity0, "equity": equity, "trades": trades, "pairs": closed, "daily": daily, "modes": modes, "params": dataclasses.asdict(p)}
