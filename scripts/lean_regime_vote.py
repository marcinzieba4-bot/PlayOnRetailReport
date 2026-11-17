"""Lean Regime Vote - command line.

  python scripts/lean_regime_vote.py backtest            # full-history backtest -> results/lean_regime_vote*.json + P&L page
  python scripts/lean_regime_vote.py plan [--equity N] [--date YYYY-MM-DD]   # today's regime and orders (JSON + table)
  python scripts/lean_regime_vote.py controls            # un-gated / inverted / no-#1-short variants for comparison
"""
import argparse, datetime as dt, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import lean_regime_vote as lrv

KEYS = ["total_return", "ann_return", "ann_vol", "sharpe", "sortino", "calmar", "max_drawdown", "longest_dd_days", "worst_day", "worst_week", "var95_daily", "cvar95_daily",
        "skew", "beta_spy", "corr_spy", "avg_gross", "avg_net", "trades", "stops", "halts", "hedge_pnl_pct"]

def show(risk):
    for k in KEYS:
        v = risk.get(k)
        print(f"  {k:18s} " + (f"{v:+.2%}" if isinstance(v, float) and k not in ("sharpe", "sortino", "calmar", "skew", "beta_spy", "corr_spy", "avg_gross", "avg_net") else f"{v:.2f}" if isinstance(v, float) else str(v)))
    for leg in ("MOM_SECTOR", "MOM_CAT", "FADE_THEME", "FADE_CATDOWN"):
        v = risk.get(f"leg_{leg}")
        if v: print(f"  leg {leg:12s} n={v['n']:3d} avg={v['avg_bp']:+5.0f}bp hit={v['hit']:.2f} pnl={v['pnl_pct_of_equity0']:+.2%} stops={v['stops']}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["backtest", "plan", "controls"]); ap.add_argument("--equity", type=float, default=100_000); ap.add_argument("--date", type=str, default=None)
    a = ap.parse_args()
    if a.cmd == "backtest":
        res, risk = lrv.backtest(equity0=a.equity)
        print(f"{lrv.STRATEGY_ID} v{lrv.VERSION}: {res['daily'][0][0]} -> {res['daily'][-1][0]}, {len(res['daily'])} sessions"); show(risk)
        subprocess.run([sys.executable, "scripts/pnl_report.py", f"results/{lrv.STRATEGY_ID}.json", f"results/{lrv.STRATEGY_ID}_report.html"], stdout=subprocess.DEVNULL)
        print(f"  -> results/{lrv.STRATEGY_ID}.json, results/{lrv.STRATEGY_ID}_risk.json, results/{lrv.STRATEGY_ID}_report.html")
    elif a.cmd == "plan":
        o = lrv.orders(dt.date.fromisoformat(a.date) if a.date else None, a.equity)
        print(f"report {o['report_date']} | MODE {o['mode']} | votes {o['votes_rate_dir']} | macro '{o['macro_subtitle'][:50]}'")
        print("sectors:", ", ".join(f"{e}:{'B' if v==1 else 'b' if v==-1 else 'm'}" for e, v in o["sectors"].items()), "| catalysts:", ", ".join(f"{t}{'↑' if d>0 else '↓'}" for t, d in o["catalysts"]))
        print("retail:", " | ".join(n[:30] for n in o["retail_top"]))
        for x in o["orders"]:
            print(f"  {x['leg']:12s} {x['symbol']:5s} " + (f"skipped ({x['skipped']})" if "skipped" in x else f"{x['side']} {x['qty']} sh (~{x['notional']:,}) ref {x['ref_close']:.2f} ATR {x['atr10']:.2%} stop {x['stop_pct']:.2%} exit after {x['exit_after_sessions']} sessions"))
        print(f"  SPY hedge notional: {o['spy_hedge_notional']:+,} (re-size each close)")
        os.makedirs("results", exist_ok=True); json.dump(o, open(f"results/{lrv.STRATEGY_ID}_plan_{o['report_date']}.json", "w"), indent=1)
    else:
        for lbl, p in [("as frozen", lrv.LeanParams()), ("no regime gate", lrv.LeanParams(force_mode="BOTH")), ("regime inverted", lrv.LeanParams(force_mode="INVERT")),
                       ("without the #1 short", lrv.LeanParams(fade_theme=False)), ("vote window 20", lrv.LeanParams(regime_k=20)), ("no hedge", lrv.LeanParams(hedge=False))]:
            res, risk = lrv.backtest(params=p, tag=f"{lrv.STRATEGY_ID}_{lbl.replace(' ', '_')}")
            print(f"{lbl:22s} total {risk['total_return']:+7.2%} sharpe {risk['sharpe']:5.2f} mdd {risk['max_drawdown']:+6.2%} beta {risk['beta_spy']:+.2f} trades {risk['trades']}")

if __name__ == "__main__":
    main()
