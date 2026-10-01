"""Produce the trade plan for the NEXT US session from the newest *available* briefing.

Point-in-time: the briefing dated D is live ~13:17 ET on D.  Run this any time
after ~13:20 ET on D (or the next morning before the open).  It never reads a
report that is not yet published and never uses the next session's prices:
the opening print is the only thing you add at 9:30 ET, and the plan tells you
exactly what to do for every possible open.

Usage:  python scripts/make_plan.py [--equity 100000] [--date YYYY-MM-DD] [--legs extension|crack|both]
"""
import argparse, datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, prices
from retailplay.mapping import map_play
from retailplay.strategy import Params, position_size


def next_session(d: dt.date, spy_daily) -> dt.date:
    # next weekday after d that is not a known holiday (approximated by SPY having traded on the
    # same weekday pattern; for the forward date we can only exclude weekends)
    n = d + dt.timedelta(days=1)
    while n.weekday() >= 5:
        n += dt.timedelta(days=1)
    return n


def weekly_plan(a):
    from retailplay.weekly import WeeklyParams
    p = WeeklyParams()
    rdate = dt.date.fromisoformat(a.date) if a.date else reports.latest_available_report()
    sec = reports.parse_retail_section(reports.html_to_text(reports.fetch_report_html(rdate)), rdate)
    today = dt.date.today()
    spy_d = prices.daily_map(prices._fetch("SPY", "1d", rdate - dt.timedelta(days=45), today))
    sess = next_session(rdate, spy_d)
    p1 = sec.plays[0]
    sym, rdir = map_play(p1.name)
    print(f"Report used : {rdate}   #1 theme: {p1.name!r} -> {sym} (retail is {'LONG' if rdir>0 else 'SHORT'})")
    print(f"Entry       : {sess} open.  Hold {p.hold} sessions, flat at the close of the {p.hold}th session.  Hedge: long SPY, equal notional.")
    if sym is None or rdir == 0:
        print("Untradeable theme this week: no trade."); return
    d = prices.daily_map(prices._fetch(sym, "1d", rdate - dt.timedelta(days=45), today))
    last = max(k for k in d if k <= rdate); pc = d[last][3]
    atr = prices.atr_pct(d, last + dt.timedelta(days=1))
    if atr is None or atr > p.max_atr:
        print(f"ATR10 {atr} unavailable or > {p.max_atr:.0%}: no trade."); return
    side = -rdir
    notional = min(a.equity * p.risk_per_trade / (p.stop_atr * atr), a.equity * p.max_notional)
    print(f"Prev close  : {pc:.2f} ({last})   ATR10 {atr:.2%}")
    print(f"Short leg   : {'SHORT' if side<0 else 'LONG'} {sym} ~{int(notional/pc)} sh (~{notional:,.0f} notional, {notional/a.equity:.0%} of equity) at {sess} open")
    print(f"Stop        : {p.stop_atr} x ATR = {p.stop_atr*atr:.2%} {'above' if side<0 else 'below'} entry, on daily high/low")
    print(f"Hedge leg   : {'LONG' if side<0 else 'SHORT'} SPY, same notional, no stop, closed with the short leg")
    print(f"Alternative : hedge with #2 theme {sec.plays[1].name!r} -> {map_play(sec.plays[1].name)[0]} (higher backtest return, less robust across phases)")
    if p1.breaks:
        print(f"Kill switch : {p1.breaks[:300].strip()}...")
    print("Rules: one pair per week; never add to a loser; if the short leg stops out, close the hedge the same day; no re-entry that week.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", type=float, default=100_000)
    ap.add_argument("--date", type=str, default=None, help="report date to use (default: newest available)")
    ap.add_argument("--legs", type=str, default=None)
    ap.add_argument("--weekly", action="store_true", help="print the weekly Retail #1 Fade pair instead of the intraday plan")
    a = ap.parse_args()
    if a.weekly:
        return weekly_plan(a)
    p = Params(legs=a.legs) if a.legs else Params()
    rdate = dt.date.fromisoformat(a.date) if a.date else reports.latest_available_report()
    html = reports.fetch_report_html(rdate)
    sec = reports.parse_retail_section(reports.html_to_text(html), rdate)
    today = dt.date.today()
    # refresh daily bars (drop cache for the few symbols we need so prev close / ATR are current)
    spy_bars = prices._fetch("SPY", "1d", rdate - dt.timedelta(days=45), today)
    spy_d = prices.daily_map(spy_bars)
    sess = next_session(rdate, spy_d)
    print(f"Report used : {rdate}  (published ~13:17 ET that day)")
    print(f"Plan for    : {sess} US cash session, 9:30 -> 15:55 ET, flat at close")
    print(f"Equity      : {a.equity:,.0f}   risk/trade {p.risk_per_trade:.1%}   daily cap {p.daily_loss_cap:.1%}   weekly cap {p.weekly_loss_cap:.1%}   legs={p.legs}")
    print()
    plan = []
    for play in sec.plays:
        sym, rdir = map_play(play.name)
        line = f"#{play.rank} {play.name!r}"
        if sym is None or rdir == 0 or play.rank > p.max_trades_per_day:
            print(line, "-> not traded (" + ("untradeable theme" if rdir == 0 or sym is None else "rank beyond max trades") + ")"); continue
        bars = prices._fetch(sym, "1d", rdate - dt.timedelta(days=45), today)
        d = prices.daily_map(bars)
        last_days = sorted(k for k in d if k <= rdate)
        if not last_days:
            print(line, f"-> {sym}: no price data"); continue
        pc_day = last_days[-1]
        pc = d[pc_day][3]
        atr = prices.atr_pct(d, pc_day + dt.timedelta(days=1))
        if atr is None:
            print(line, f"-> {sym}: not enough history for ATR"); continue
        if atr > p.max_atr:
            print(line, f"-> {sym}: ATR10 {atr:.1%} > {p.max_atr:.0%}, skipped (too wild)"); continue
        thr = p.gap_atr * atr
        up_lvl, dn_lvl = pc * (1 + thr), pc * (1 - thr)
        stop_d, tgt_d = p.stop_atr * atr, p.target_atr * atr
        print(f"{line} -> {sym}  retail is {'LONG' if rdir>0 else 'SHORT'}   prev close {pc:.2f} ({pc_day})   ATR10 {atr:.2%}")
        if p.legs in ("both", "extension" if rdir > 0 else "crack"):
            qty = position_size(a.equity, up_lvl, up_lvl * (1 + stop_d), p)
            print(f"      if OPEN >= {up_lvl:.2f} (gap up > +{thr:.2%}):  SHORT {qty} sh at open | stop +{stop_d:.2%} above entry | target max(prev close, entry-{tgt_d:.2%}) | else flat 15:55")
        if p.legs in ("both", "crack" if rdir > 0 else "extension"):
            qty = position_size(a.equity, dn_lvl, dn_lvl * (1 - stop_d), p)
            print(f"      if OPEN <= {dn_lvl:.2f} (gap down < -{thr:.2%}):  LONG {qty} sh at open  | stop -{stop_d:.2%} below entry | target min(prev close, entry+{tgt_d:.2%}) | else flat 15:55"
                  f"  [skip if SPY opens < {p.spy_panic_gap:+.1%}]")
        print(f"      otherwise (open between {dn_lvl:.2f} and {up_lvl:.2f}): NO TRADE")
        if play.breaks:
            print(f"      report kill-switch: {play.breaks[:220].strip()}...")
        plan.append({"rank": play.rank, "play": play.name, "symbol": sym, "retail_dir": rdir, "prev_close": pc, "atr10": atr,
                     "short_if_open_ge": up_lvl, "long_if_open_le": dn_lvl, "stop_pct": stop_d, "target_pct_cap": tgt_d})
        print()
    os.makedirs("results", exist_ok=True)
    out = {"report_date": rdate.isoformat(), "session": sess.isoformat(), "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "params": str(p), "plan": plan}
    json.dump(out, open(f"results/plan_{sess.isoformat()}.json", "w"), indent=1)
    print("Hard rules: max 2 trades/day (rank 1 & 2 only); no new trade after a -1% day or a -2.5% week; never hold overnight;"
          " skip single names reporting earnings that day; if a position hits the stop, do not re-enter that name.")


if __name__ == "__main__":
    main()
