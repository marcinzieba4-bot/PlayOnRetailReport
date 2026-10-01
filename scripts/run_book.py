"""Simulate the Narrative Rotation book across leg combinations."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, book
from retailplay.book import BookParams

def main():
    secs = reports.load_sections()
    S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    H = "2026-08-12"
    variants = [
        ("book_all_hedged", BookParams()),
        ("book_all_unhedged", BookParams(hedge=False)),
        ("book_S1_only", BookParams(leg_lp=False, leg_dr=False)),
        ("book_S1_warn_only", BookParams(leg_lp=False, leg_dr=False, warn_min=0.49)),
        ("book_LP_only", BookParams(leg_s1=False, leg_dr=False)),
        ("book_LP_rank2_only", BookParams(leg_s1=False, leg_dr=False, lp_ranks=(2,))),
        ("book_DR_only", BookParams(leg_s1=False, leg_lp=False)),
        ("book_S1_LP", BookParams(leg_dr=False)),
        ("book_S1_DR", BookParams(leg_lp=False)),
        ("book_all_nostop", BookParams(stop_atr=99)),
        ("book_all_hold10", BookParams(hold=10)),
        ("book_all_hold3", BookParams(hold=3)),
    ]
    out = {}
    print(f"{'variant':22s} {'trades':>6s} {'total':>7s} {'mdd':>6s} {'sharpe':>6s} {'gross':>5s} {'H1':>6s} {'H2':>6s} | legs: n / avg bp / hit / t")
    for label, p in variants:
        res = book.run(S, start, end, p)
        sm = book.summarize(res, split=H); out[label] = sm
        json.dump(res, open(f"results/{label}.json", "w"), indent=1, default=str)
        legs = "  ".join(f"{L}: {sm.get(L+'_n',0)}/{sm.get(L+'_avg_bp',0):+.0f}/{sm.get(L+'_hit',0):.2f}/{sm.get(L+'_t',0):+.1f}" for L in ("S1", "LP", "DR") if sm.get(L+'_n'))
        print(f"{label:22s} {sm['n']:6d} {sm.get('total_return',0):+7.1%} {sm.get('max_drawdown',0):+6.1%} {sm.get('sharpe',0):6.2f} {sm.get('avg_gross',0):5.2f} {sm.get('H1_return',0):+6.1%} {sm.get('H2_return',0):+6.1%} | {legs}")
    json.dump(out, open("results/book_summary.json", "w"), indent=1)

if __name__ == "__main__":
    main()
