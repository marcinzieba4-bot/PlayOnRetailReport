"""Backtest the weekly Retail #1 Fade across hedges, schedules (all 5 phases) and ex-gold."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, weekly
from retailplay.weekly import WeeklyParams

def main():
    secs = reports.load_sections()
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    os.makedirs("results", exist_ok=True)
    out = {}
    variants = [("weekly_spyhedge", WeeklyParams()), ("weekly_rank2hedge", WeeklyParams(hedge="rank2")), ("weekly_nohedge", WeeklyParams(hedge="none")),
                ("weekly_spyhedge_exGLD", WeeklyParams(exclude=("GLD",))), ("weekly_rank2hedge_exGLD", WeeklyParams(hedge="rank2", exclude=("GLD",))),
                ("weekly_spyhedge_nostop", WeeklyParams(stop_atr=99, max_notional=0.3))]
    variants += [(f"rolling_phase{k}_spyhedge", WeeklyParams(schedule="rolling", phase=k)) for k in range(5)]
    variants += [(f"rolling_phase{k}_rank2hedge", WeeklyParams(schedule="rolling", phase=k, hedge="rank2")) for k in range(5)]
    for label, p in variants:
        res = weekly.run(S, start, end, p)
        sm = weekly.summarize(res); out[label] = sm
        json.dump(res, open(f"results/{label}.json", "w"), indent=1)
        print(f"{label:28s} n={sm.get('n',0):2d} hit={sm.get('hit',0):.2f} avg={sm.get('avg_ret_pct',0):+.2f}%/trade t={sm.get('t',0):5.2f} | short leg {sm.get('short_leg_avg_pct',0):+.2f}% hit={sm.get('short_leg_hit',0):.2f} t={sm.get('short_leg_t',0):5.2f} | tot={sm.get('total_return',0):+.1%} mdd={sm.get('max_drawdown',0):+.1%} stops={sm.get('stops',0)}")
    json.dump(out, open("results/weekly_summary.json", "w"), indent=1)
    tr = json.load(open("results/weekly_spyhedge.json"))["trades"]
    print("\nweekly_spyhedge trades:")
    for t in tr:
        print(f"  {t['entry_day']} {t['symbol']:5s} side={t['side']:+d} {t['ret_short_leg']*100:+5.1f}% {t['exit_reason']:6s} hedge {t['ret_hedge_leg']*100:+5.1f}%  total {t['ret_total']*100:+5.2f}%  [{t['play'][:40]}]")

if __name__ == "__main__":
    main()
