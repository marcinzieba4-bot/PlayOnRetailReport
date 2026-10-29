"""The lean regime book (README section 14) in full, plus the persisting #3/#4 long vs SPY by regime."""
import datetime as dt, json, os, sys, math, statistics as st
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, prices, regime_book, context
from retailplay.regime_book import RegimeParams
from retailplay.book import risk_report
from retailplay.mapping import map_play

LEAN = dict(mom_theme=False, fade_new2=False, fade_long34=False)
PERIODS = [("2025-08-01", "2025-12-01", "Aug-Nov25"), ("2025-12-01", "2026-06-01", "Dec-May26"), ("2026-06-01", "2026-12-01", "Jun-Oct26")]

def periods(res):
    out = {}
    for a, b, l in PERIODS:
        r = [(d[1] + d[2]) / (d[3] - d[1] - d[2]) for d in res["daily"] if a <= d[0] < b]
        if r:
            out[l] = (math.prod(1 + x for x in r) - 1, (st.mean(r) / st.pstdev(r) * math.sqrt(252)) if st.pstdev(r) else 0)
    return out

def main():
    secs = reports.load_sections(); S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    T = {d: reports.html_to_text(open(f"data/reports/{d}.html").read()) for d in S}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end))
    # ---------- 1. the lean book in full
    res = regime_book.run(S, T, start, end, RegimeParams(**LEAN)); rep = risk_report(res, spy, split="2026-06-01")
    json.dump(res, open("results/REG_lean.json", "w"), indent=1, default=str); json.dump(rep, open("results/REG_lean_risk.json", "w"), indent=1)
    print("=== LEAN REGIME BOOK: easing -> long Bullish sectors + ↑ catalysts vs SPY; tightening -> short #1 theme + long ↓ catalysts; neutral -> nothing ===")
    for k in ["total_return", "ann_return", "ann_vol", "sharpe", "sortino", "max_drawdown", "calmar", "longest_dd_days", "worst_day", "best_day", "worst_week", "best_week", "weekly_hit",
              "var95_daily", "var99_daily", "cvar95_daily", "skew", "beta_spy", "corr_spy", "spy_total_return_same_period", "avg_gross", "max_gross", "avg_net", "max_abs_net", "avg_positions",
              "pct_days_in_market", "trades", "stops", "halts", "days_blocked", "hedge_pnl_pct"]:
        v = rep.get(k); print(f"  {k:30s} {v:+.2%}" if isinstance(v, float) and abs(v) < 5 and k not in ("sharpe","sortino","calmar","skew","beta_spy","corr_spy","avg_gross","max_gross","avg_net","max_abs_net","avg_positions") else f"  {k:30s} {v:.2f}" if isinstance(v, float) else f"  {k:30s} {v}")
    print("  periods:", "  ".join(f"{l} {r:+.1%} (Sharpe {sh:.1f})" for l, (r, sh) in periods(res).items()))
    print("\n  leg attribution:")
    for leg in ("MOM_SECTOR", "MOM_CAT", "FADE_THEME", "FADE_CATDOWN"):
        v = rep.get(f"leg_{leg}")
        if v: print(f"    {leg:12s} n={v['n']:3d} avg={v['avg_bp']:+5.0f}bp hit={v['hit']:.2f} t={v['t']:+.2f} pnl={v['pnl_pct_of_equity0']:+.2%} stops={v['stops']}")
    m = defaultdict(float); mm = defaultdict(Counter)
    for d in res["daily"]: m[d[0][:7]] += d[1] + d[2]
    for d, mo in res["modes"].items(): mm[d[:7]][mo[0]] += 1
    print("\n  month    pnl$   M/N/F")
    for k in sorted(m): print(f"    {k} {m[k]:+7.0f}   {mm[k]['M']:2d}/{mm[k]['N']:2d}/{mm[k]['F']:2d}")
    print(f"\n  trades ({len(res['trades'])}):")
    for t in res["trades"]:
        print(f"    {t['entry_day']} {t['exit_day']} {t['leg']:12s} {t['sym']:5s} {'SHORT' if t['side']<0 else 'LONG '} {t['exit_reason']:4s} {t['ret']*100:+6.1f}%  {t['play'][:38]}")
    # ---------- 2. persisting #3/#4 vs SPY by regime: raw
    REG = {d: context.regime(T[d]) for d in S}; MODE = {d: mo for d, (mo, sc) in context.regime_series(REG, "text", 10).items()}
    D = {}
    def dm(sym):
        if sym not in D:
            try: D[sym] = prices.daily_map(prices.get_bars(sym, "1d", start - dt.timedelta(days=45), end))
            except Exception: D[sym] = {}
        return D[sym]
    td = sorted(spy); nxt = lambda d: next((t for t in td if t > d), None)
    def ex(sym, R, h):
        Tn = nxt(R); d = dm(sym)
        if Tn is None: return None
        i = td.index(Tn)
        if i + h >= len(td) or Tn not in d or td[i + h] not in d: return None
        return (d[td[i + h]][3] / d[Tn][0] - 1) - (spy[td[i + h]][3] / spy[Tn][0] - 1)
    def listed(sym, R):
        pr = R - dt.timedelta(days=1)
        while pr not in S and (R - pr).days < 4: pr -= dt.timedelta(days=1)
        return pr in S and sym in [map_play(q.name)[0] for q in S[pr]]
    def stats(xs):
        xs = [x for x in xs if x is not None]
        if len(xs) < 5: return f"n={len(xs)}"
        mu = st.mean(xs); sd = st.pstdev(xs); return f"n={len(xs):3d} {mu*1e4:+6.0f}bp hit={sum(x>0 for x in xs)/len(xs):.2f} t={mu/(sd/math.sqrt(len(xs))) if sd else 0:+.2f}"
    print("\n=== PERSISTING #3/#4 LONG vs SPY, raw forward excess by regime vote ===")
    for mode in ("MOMENTUM", "NEUTRAL", "FADE", "ALL"):
        for lbl, f in [("persisting #3/#4", lambda q, s, R: listed(s, R)), ("NEW #3/#4", lambda q, s, R: not listed(s, R))]:
            row = []
            for h in (5, 10, 20):
                xs = []
                for R in sorted(S):
                    if mode != "ALL" and MODE[R] != mode: continue
                    for q in S[R][2:4]:
                        s_, d_ = map_play(q.name)
                        if s_ and d_ == 1 and f(q, s_, R): xs.append(ex(s_, R, h))
                row.append(f"{h}d: {stats(xs)}")
            print(f"  {mode:9s} {lbl:17s} | " + " | ".join(row))
    # ---------- 3. persisting #3/#4 as an event-level leg (only this leg), by mode
    print("\n=== PERSISTING #3/#4 LONG as the only leg, event-level (hold 5, 2 ATR stop, SPY-hedged) ===")
    print(f"  {'active in':28s} {'total':>7s} {'sharpe':>6s} {'mdd':>7s} {'n':>4s} {'avg':>6s} {'hit':>5s}  periods")
    for lbl, modes in [("FADE only", ("FADE",)), ("MOMENTUM only", ("MOMENTUM",)), ("NEUTRAL only", ("NEUTRAL",)), ("all modes (no regime)", ("MOMENTUM", "NEUTRAL", "FADE"))]:
        p = RegimeParams(mom_theme=False, mom_sector=False, mom_cat=False, fade_theme=False, fade_new2=False, fade_cat_down=False, fade_long34=True, long34_modes=modes)
        r_ = regime_book.run(S, T, start, end, p); rp = risk_report(r_, spy)
        legs = [t for t in r_["trades"]]; rets = [t["ret"] for t in legs]
        print(f"  {lbl:28s} {rp['total_return']:+7.2%} {rp['sharpe']:6.2f} {rp['max_drawdown']:+7.2%} {len(legs):4d} {st.mean(rets)*1e4 if rets else 0:+6.0f} {sum(x>0 for x in rets)/len(rets) if rets else 0:5.2f}  " + "  ".join(f"{l} {r:+.1%}" for l, (r, sh) in periods(r_).items()))
    for lbl, modes, hold in [("FADE only, hold 10", ("FADE",), 10), ("all modes, hold 10", ("MOMENTUM", "NEUTRAL", "FADE"), 10)]:
        p = RegimeParams(mom_theme=False, mom_sector=False, mom_cat=False, fade_theme=False, fade_new2=False, fade_cat_down=False, fade_long34=True, long34_modes=modes, hold_theme=hold)
        r_ = regime_book.run(S, T, start, end, p); rp = risk_report(r_, spy); rets = [t["ret"] for t in r_["trades"]]
        print(f"  {lbl:28s} {rp['total_return']:+7.2%} {rp['sharpe']:6.2f} {rp['max_drawdown']:+7.2%} {len(rets):4d} {st.mean(rets)*1e4 if rets else 0:+6.0f} {sum(x>0 for x in rets)/len(rets) if rets else 0:5.2f}  " + "  ".join(f"{l} {r:+.1%}" for l, (r, sh) in periods(r_).items()))
    # ---------- 4. lean book + persisting #3/#4 in FADE (and in all modes)
    print("\n=== LEAN BOOK + persisting #3/#4 long ===")
    for lbl, modes in [("lean + #3/#4 in FADE", ("FADE",)), ("lean + #3/#4 in all modes", ("MOMENTUM", "NEUTRAL", "FADE"))]:
        p = RegimeParams(mom_theme=False, fade_new2=False, fade_long34=True, long34_modes=modes)
        r_ = regime_book.run(S, T, start, end, p); rp = risk_report(r_, spy)
        print(f"  {lbl:28s} {rp['total_return']:+7.2%} sharpe {rp['sharpe']:5.2f} mdd {rp['max_drawdown']:+6.2%} trades {rp['trades']:3d}  " + "  ".join(f"{l} {r:+.1%}" for l, (r, sh) in periods(r_).items()))

if __name__ == "__main__":
    main()
