"""Regime-switched pair book: variants, risk report, attribution, monthly P&L."""
import datetime as dt, json, os, sys
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, prices, pair_book
from retailplay.pair_book import PairParams
from retailplay.book import risk_report

def main():
    secs = reports.load_sections()
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    T = {d: reports.html_to_text(open(f"data/reports/{d}.html").read()) for d in S}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end))
    variants = [
        ("PAIR_base", PairParams()),
        ("PAIR_fade_only", PairParams(pm1=False, pm2=False, pm3=False)),
        ("PAIR_mom_only", PairParams(pf1=False, pf2=False)),
        ("PAIR_no_F1", PairParams(pf1=False)), ("PAIR_no_F2", PairParams(pf2=False)),
        ("PAIR_no_M1", PairParams(pm1=False)), ("PAIR_no_M2", PairParams(pm2=False)), ("PAIR_no_M3", PairParams(pm3=False)),
        ("PAIR_hold_short", PairParams(hold_f1=5, hold_f2=10, hold_m1=5, hold_m2=5, hold_m3=10)),
        ("PAIR_hold_long", PairParams(hold_f1=20, hold_f2=30, hold_m1=20, hold_m2=20, hold_m3=30)),
        ("PAIR_stop1.5", PairParams(stop_mult=1.5)), ("PAIR_stop4", PairParams(stop_mult=4.0)), ("PAIR_nostop", PairParams(stop_mult=99)),
        ("PAIR_no_hedge", PairParams(hedge_residual=False)),
        ("PAIR_k5", PairParams(regime_k=5)), ("PAIR_k20", PairParams(regime_k=20)),
        ("PAIR_2x_risk", PairParams(risk_per_atr=0.008, max_notional=0.4)),
    ]
    KEYS = ["total_return", "ann_vol", "sharpe", "sortino", "max_drawdown", "calmar", "longest_dd_days", "worst_day", "worst_week", "var95_daily", "cvar95_daily",
            "skew", "beta_spy", "corr_spy", "avg_gross", "max_gross", "avg_net", "trades", "stops", "halts", "H1_return", "H2_return", "H1_sharpe", "H2_sharpe"]
    reps = {}
    for label, p in variants:
        res = pair_book.run(S, T, start, end, p)
        rep = risk_report(res, spy, split="2026-06-01"); reps[label] = rep
        json.dump(res, open(f"results/{label}.json", "w"), indent=1, default=str)
    json.dump(reps, open("results/pair_risk_report.json", "w"), indent=1)
    labels = [l for l, _ in variants]
    def fmt(k, v):
        if isinstance(v, float):
            return f"{v:6.2f}" if k in ("sharpe", "sortino", "calmar", "skew", "beta_spy", "corr_spy", "avg_gross", "max_gross", "avg_net", "H1_sharpe", "H2_sharpe") else f"{v:+7.2%}"
        return f"{v}"
    print(f"{'metric':14s}" + "".join(f"{l[5:][:11]:>12s}" for l in labels))
    for k in KEYS:
        print(f"{k:14s}" + "".join(f"{fmt(k, reps[l].get(k, float('nan'))):>12s}" for l in labels))
    base = json.load(open("results/PAIR_base.json"))
    print("\nPAIR_base attribution by pair type (ret = pair P&L / long-leg notional):")
    for kind in ("P_F1", "P_F2", "P_M1", "P_M2", "P_M3"):
        v = reps["PAIR_base"].get(f"leg_{kind}")
        if v: print(f"  {kind} n={v['n']:3d} avg={v['avg_bp']:+5.0f}bp hit={v['hit']:.2f} t={v['t']:+.2f} stops={v['stops']}   pnl$={sum(c['pnl'] for c in base['pairs'] if c['kind']==kind):+,.0f}")
    m = defaultdict(float); mm = defaultdict(Counter)
    for d in base["daily"]:
        m[d[0][:7]] += d[1] + d[2]
    for d, mo in base["modes"].items():
        mm[d[:7]][mo] += 1
    print("\nmonth   pnl$    modes")
    for k in sorted(m):
        print(f"  {k} {m[k]:+7.0f}   {dict(mm[k])}")

if __name__ == "__main__":
    main()
