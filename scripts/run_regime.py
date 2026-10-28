"""Regime-Switched Narrative Book: variants, risk report, monthly P&L, mode calendar."""
import datetime as dt, json, os, sys
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, prices, regime_book
from retailplay.regime_book import RegimeParams
from retailplay.book import risk_report

def main():
    secs = reports.load_sections()
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    T = {d: reports.html_to_text(open(f"data/reports/{d}.html").read()) for d in S}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end))
    variants = [
        ("REG_text", RegimeParams()),
        ("REG_text_mom_only", RegimeParams(fade_theme=False, fade_new2=False, fade_long34=False, fade_cat_down=False)),
        ("REG_text_fade_only", RegimeParams(mom_theme=False, mom_sector=False, mom_cat=False)),
        ("REG_text_no_catdown", RegimeParams(fade_cat_down=False)),
        ("REG_text_no_new2", RegimeParams(fade_new2=False)),
        ("REG_text_no_long34", RegimeParams(fade_long34=False)),
        ("REG_text_fade_sector_on", RegimeParams(fade_sector=True)),
        ("REG_text_k5", RegimeParams(regime_k=5)),
        ("REG_text_k20", RegimeParams(regime_k=20)),
        ("REG_composite", RegimeParams(regime_method="composite")),
        ("REG_fixed_legacy", RegimeParams(regime_method="fixed", use_y10=True)),
        ("REG_text_no_risk_rules", RegimeParams(stop_atr=99, daily_loss_halt=9, dd_halve=9, dd_stop=9)),
    ]
    KEYS = ["total_return", "ann_vol", "sharpe", "sortino", "max_drawdown", "calmar", "worst_day", "worst_week", "var95_daily", "cvar95_daily",
            "skew", "beta_spy", "corr_spy", "avg_gross", "max_gross", "avg_net", "trades", "stops", "halts", "H1_return", "H2_return", "H1_sharpe", "H2_sharpe"]
    reps = {}
    for label, p in variants:
        res = regime_book.run(S, T, start, end, p)
        rep = risk_report(res, spy, split="2026-06-01"); reps[label] = rep
        json.dump(res, open(f"results/{label}.json", "w"), indent=1, default=str)
    json.dump(reps, open("results/regime_risk_report.json", "w"), indent=1)
    labels = [l for l, _ in variants]
    def fmt(k, v):
        if isinstance(v, float):
            return f"{v:6.2f}" if k in ("sharpe", "sortino", "calmar", "skew", "beta_spy", "corr_spy", "avg_gross", "max_gross", "avg_net", "H1_sharpe", "H2_sharpe") else f"{v:+7.2%}"
        return f"{v}"
    print(f"{'metric':14s}" + "".join(f"{l[4:][:15]:>16s}" for l in labels))
    for k in KEYS:
        print(f"{k:14s}" + "".join(f"{fmt(k, reps[l].get(k, float('nan'))):>16s}" for l in labels))
    base = json.load(open("results/REG_text.json"))
    print("\nREG_text leg attribution:")
    for leg in ("MOM_THEME", "MOM_SECTOR", "MOM_CAT", "FADE_THEME", "FADE_NEW2", "FADE_LONG34", "FADE_CATDOWN", "FADE_SECTOR"):
        v = reps["REG_text"].get(f"leg_{leg}")
        if v: print(f"  {leg:12s} n={v['n']:3d} avg={v['avg_bp']:+5.0f}bp hit={v['hit']:.2f} t={v['t']:+.2f} pnl={v['pnl_pct_of_equity0']:+.2%} stops={v['stops']}")
    m = defaultdict(float); mm = defaultdict(Counter)
    for d in base["daily"]:
        m[d[0][:7]] += d[1] + d[2]
    for d, mo in base["modes"].items():
        mm[d[:7]][mo] += 1
    print("\nmonth   pnl$    modes")
    for k in sorted(m):
        print(f"  {k} {m[k]:+7.0f}   {dict(mm[k])}")
    print("\nmode share:", Counter(base["modes"].values()))

if __name__ == "__main__":
    main()
