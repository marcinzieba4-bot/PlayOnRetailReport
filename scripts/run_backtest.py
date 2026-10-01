"""Run the Retail Gap Fade backtest over the whole archive and write results/."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, backtest
from retailplay.strategy import Params

def main():
    secs = reports.load_sections()
    json.dump([s.to_dict() for s in secs], open("data/retail_plays.json", "w"), indent=1)
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    start, end = min(S) + dt.timedelta(days=1), max(S)  # last full session <= last report date
    os.makedirs("results", exist_ok=True)
    out = {}
    for label, iv, ranks, p in [
        # default configuration (what scripts/make_plan.py uses)
        ("default_extension_1h_rank12", "1h", (1, 2), Params()),
        ("default_extension_15m_rank12", "15m", (1, 2), Params()),
        # the a-priori two-leg version and its pieces
        ("both_legs_1h_rank12", "1h", (1, 2), Params(legs="both")),
        ("crack_only_1h_rank12", "1h", (1, 2), Params(legs="crack")),
        ("both_legs_1h_rank1", "1h", (1,), Params(legs="both")),
        ("both_legs_1h_rank1234", "1h", (1, 2, 3, 4), Params(legs="both", max_trades_per_day=4)),
        # risk-management sensitivity
        ("both_legs_nostop_1h", "1h", (1, 2), Params(legs="both", stop_atr=99, target_atr=99, notional_frac=0.35)),
        ("both_legs_tight_1h", "1h", (1, 2), Params(legs="both", stop_atr=0.4, target_atr=0.8)),
        ("both_legs_gap0.5_1h", "1h", (1, 2), Params(legs="both", gap_atr=0.5)),
        ("extension_gap0.5_1h", "1h", (1, 2), Params(gap_atr=0.5)),
    ]:
        res = backtest.run(S, start, end, iv, p, ranks=ranks)
        summ = backtest.summarize(res)
        out[label] = summ
        json.dump(res, open(f"results/{label}.json", "w"), indent=1, default=str)
        print(f"{label:28s} n={summ.get('n',0):3d} hit={summ.get('hit',0):.2f} avg={summ.get('avg_ret_bp',0):6.1f}bp t={summ.get('t_stat',0):5.2f} "
              f"PF={summ.get('profit_factor',0):4.2f} tot={summ.get('total_return',0):+.2%} mdd={summ.get('max_drawdown',0):+.2%} sharpe={summ.get('sharpe_daily',float('nan')):4.2f} exits={summ.get('exits')}")
    json.dump(out, open("results/summary.json", "w"), indent=1)

if __name__ == "__main__":
    main()
