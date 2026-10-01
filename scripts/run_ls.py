"""Narrative Long/Short with portfolio risk management: configurations + full risk report."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, book, prices
from retailplay.book import BookParams

LS = dict(leg_s1=True, leg_lp=True, leg_dr=False, hedge=True, size_mode="vol", risk_per_atr=0.004, max_notional=0.25,
          stop_atr=1.5, hold=5, gross_cap=1.0, daily_loss_halt=0.015, dd_halve=0.06, dd_stop=0.10, s1_fear_scale=0.5)

CONFIGS = [
    ("LS_base", BookParams(**LS)),
    ("LS_greed_only_short", BookParams(**{**LS, "s1_fear_scale": 0.0})),
    ("LS_hold10", BookParams(**{**LS, "hold": 10})),
    ("LS_short_only_vs_SPY", BookParams(**{**LS, "leg_lp": False})),
    ("LS_long_only_vs_SPY", BookParams(**{**LS, "leg_s1": False})),
    ("LS_no_hedge", BookParams(**{**LS, "hedge": False})),
    ("LS_no_risk_rules", BookParams(**{**LS, "stop_atr": 99, "daily_loss_halt": 9, "dd_halve": 9, "dd_stop": 9})),
    ("LS_2x_risk", BookParams(**{**LS, "risk_per_atr": 0.008, "max_notional": 0.5})),
]
KEYS = ["total_return", "ann_return", "ann_vol", "sharpe", "sortino", "max_drawdown", "calmar", "longest_dd_days", "worst_day", "worst_week",
        "var95_daily", "cvar95_daily", "skew", "beta_spy", "corr_spy", "avg_gross", "max_gross", "avg_net", "max_abs_net", "avg_positions",
        "pct_days_in_market", "trades", "stops", "halts", "days_blocked", "hedge_pnl_pct", "H1_return", "H2_return", "H1_sharpe", "H2_sharpe"]

def fmt(k, v):
    if isinstance(v, float):
        if k in ("sharpe", "sortino", "calmar", "skew", "beta_spy", "corr_spy", "avg_positions", "avg_gross", "max_gross", "avg_net", "max_abs_net", "H1_sharpe", "H2_sharpe"):
            return f"{v:6.2f}"
        return f"{v:+7.2%}"
    return f"{v}"

def main():
    secs = reports.load_sections()
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end))
    reps = {}
    for label, p in CONFIGS:
        res = book.run(S, start, end, p)
        rep = book.risk_report(res, spy, split="2026-08-12"); reps[label] = rep
        json.dump(res, open(f"results/{label}.json", "w"), indent=1, default=str)
    json.dump(reps, open("results/ls_risk_report.json", "w"), indent=1)
    labels = [l for l, _ in CONFIGS]
    print(f"{'metric':22s}" + "".join(f"{l[:20]:>21s}" for l in labels))
    for k in KEYS:
        print(f"{k:22s}" + "".join(f"{fmt(k, reps[l].get(k, float('nan'))):>21s}" for l in labels))
    print("\nLeg attribution (LS_base):")
    for leg in ("S1", "LP"):
        v = reps["LS_base"].get(f"leg_{leg}")
        if v: print(f"  {leg}: n={v['n']} avg={v['avg_bp']:+.0f}bp hit={v['hit']:.2f} t={v['t']:+.2f} pnl={v['pnl_pct_of_equity0']:+.2%} stops={v['stops']}")
    print(f"  hedge pnl: {reps['LS_base']['hedge_pnl_pct']:+.2%}   SPY same period: {reps['LS_base']['spy_total_return_same_period']:+.2%}")
    # equity curve, weekly
    res = json.load(open("results/LS_base.json"))
    print("\nLS_base weekly equity (end of ISO week):")
    last = {}
    for d in res["daily"]:
        y, w, _ = dt.date.fromisoformat(d[0]).isocalendar(); last[(y, w)] = (d[0], d[3])
    for (y, w), (d, e) in sorted(last.items()):
        print(f"  {d}  {e:,.0f}  {'#' * int(max(e - 100000, 0) / 100)}{'-' * int(max(100000 - e, 0) / 100)}")

if __name__ == "__main__":
    main()
