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


def ls_plan(a):
    import dataclasses
    from retailplay.book import BookParams
    from retailplay.sentiment import features
    p = BookParams(leg_s1=True, leg_lp=True, leg_dr=False, hedge=True, size_mode="vol", risk_per_atr=0.004, max_notional=0.25,
                   stop_atr=1.5, hold=5, gross_cap=1.0, daily_loss_halt=0.015, dd_halve=0.06, dd_stop=0.10, s1_fear_scale=0.5)
    rdate = dt.date.fromisoformat(a.date) if a.date else reports.latest_available_report()
    sec = reports.parse_retail_section(reports.html_to_text(reports.fetch_report_html(rdate)), rdate)
    try:
        prev = reports.parse_retail_section(reports.html_to_text(reports.fetch_report_html(rdate - dt.timedelta(days=1))), rdate - dt.timedelta(days=1))
        prev_syms = {map_play(q.name)[0] for q in prev.plays}
    except Exception:
        prev_syms = set()
    today = dt.date.today()
    spy_d = prices.daily_map(prices._fetch("SPY", "1d", rdate - dt.timedelta(days=45), today))
    sess = next_session(rdate, spy_d)
    print(f"Report used : {rdate}   orders for the {sess} open   equity {a.equity:,.0f}")
    print(f"Risk rules  : 1 ATR move = {p.risk_per_atr:.1%} of equity (cap {p.max_notional:.0%}/name) | stop {p.stop_atr} ATR | hold {p.hold} sessions | gross cap {p.gross_cap:.0%} | "
          f"daily halt {p.daily_loss_halt:.1%} | size halved beyond {p.dd_halve:.0%} DD, no entries beyond {p.dd_stop:.0%} DD | SPY hedge to net zero")
    orders = []
    for q in sec.plays:
        sym, rdir = map_play(q.name)
        if not sym or not rdir:
            print(f"  #{q.rank} {q.name!r}: untradeable, skip"); continue
        f = features(dataclasses.asdict(q))
        leg, side, scale = None, 0, 1.0
        if q.rank == 1:
            leg, side, scale = "S1 short #1", -rdir, (1.0 if f["fear_theme"] == 0 else p.s1_fear_scale)
        elif q.rank in p.lp_ranks and sym in prev_syms:
            leg, side = "LP long persisting", rdir
        if leg is None:
            print(f"  #{q.rank} {q.name!r} -> {sym}: new theme at rank {q.rank}, no order"); continue
        d = prices.daily_map(prices._fetch(sym, "1d", rdate - dt.timedelta(days=45), today))
        last = max(k for k in d if k <= rdate); pc = d[last][3]
        atr = prices.atr_pct(d, last + dt.timedelta(days=1))
        if atr is None or atr > p.max_atr or pc < p.min_price:
            print(f"  #{q.rank} {q.name!r} -> {sym}: ATR {atr} out of bounds, skip"); continue
        notional = min(a.equity * p.risk_per_atr / atr, a.equity * p.max_notional) * scale
        qty = int(notional / pc)
        theme = "greed" if f["fear_theme"] == 0 else "fear"
        print(f"  #{q.rank} {leg:20s} {sym:5s} {'SELL' if side<0 else 'BUY'} ~{qty} sh (~{notional:,.0f}, {notional/a.equity:.0%} eq) at open | ref close {pc:.2f} | ATR10 {atr:.2%} | "
              f"stop {p.stop_atr*atr:.2%} {'above' if side<0 else 'below'} entry | exit close of session 5 | theme={theme} warn={f['warn']:.2f}")
        orders.append(dict(rank=q.rank, leg=leg, symbol=sym, side=side, qty=qty, notional=notional, ref_close=pc, atr=atr, stop_pct=p.stop_atr * atr))
    net = sum(o["side"] * o["notional"] for o in orders)
    print(f"  HEDGE: {'BUY' if net<0 else 'SELL'} SPY ~{abs(net):,.0f} notional (book net {net/a.equity:+.0%} before hedge); re-size at every close.")
    os.makedirs("results", exist_ok=True)
    json.dump({"report_date": rdate.isoformat(), "session": sess.isoformat(), "orders": orders, "hedge_notional": -net}, open(f"results/ls_plan_{sess.isoformat()}.json", "w"), indent=1)


def regime_plan(a):
    import dataclasses
    from retailplay import context
    from retailplay.regime_book import RegimeParams, modes_for
    from retailplay.sentiment import features
    p = RegimeParams()
    rdate = dt.date.fromisoformat(a.date) if a.date else reports.latest_available_report()
    # the regime read is smoothed over the last regime_k reports, so load them
    hist = [d for d in reports.list_archive_dates() if d <= rdate][-max(p.regime_k, 25):]
    texts = {d: reports.html_to_text(reports.fetch_report_html(d)) for d in hist}
    regs = {d: context.regime(texts[d]) for d in hist}
    mode = modes_for(regs, p)[rdate]
    text = texts[rdate]; sec = reports.parse_retail_section(text, rdate); reg = regs[rdate]
    prev_syms = {map_play(q.name)[0] for q in reports.parse_retail_section(texts[hist[-2]], hist[-2]).plays} if len(hist) > 1 else set()
    today = dt.date.today()
    spy_d = prices.daily_map(prices._fetch("SPY", "1d", rdate - dt.timedelta(days=45), today)); sess = next_session(rdate, spy_d)
    print(f"Report used : {rdate}   orders for the {sess} open   equity {a.equity:,.0f}")
    print(f"Macro read  : subtitle '{reg['subtitle']}' | rate_dir={reg['rate_dir']:+d} (−1 cut, +1 hike) | liquidity words ease={reg['ease_words']} tight={reg['tight_words']} | 10Y={reg['y10']} | VIX={reg['vix']}")
    votes = [regs[d]['rate_dir'] for d in hist[-p.regime_k:]]
    print(f"Regime      : method={p.regime_method}, last {p.regime_k} reports rate_dir votes {votes} -> MODE = {mode}")
    stances = context.sector_stances(text); cats = context.catalysts(text)
    print("Sectors     : " + ", ".join(f"{e}:{'B' if v==1 else 'b' if v==-1 else 'm'}" for e, v in stances.items()) + "   (B bullish, b bearish, m mixed)")
    print("Catalysts   : " + ", ".join(f"{t}{'↑' if d>0 else '↓'}" for t, d in cats))
    print("Retail      : " + " | ".join(f"#{q.rank} {q.name[:34]!r}->{map_play(q.name)[0]}{' (persisting)' if map_play(q.name)[0] in prev_syms else ' (new)'}" for q in sec.plays))
    sig = []
    p1 = sec.plays[0]; sym, rdir = map_play(p1.name); f = features(dataclasses.asdict(p1)) if sym else None
    if mode == "MOMENTUM":
        if sym and rdir: sig.append(("MOM_THEME", sym, rdir, p.hold_theme, 1.0, p1.name))
        sig += [("MOM_SECTOR", e, 1, p.hold_sector, 0.5, "Bullish " + e) for e, v in stances.items() if v == 1]
        sig += [("MOM_CAT", t, 1, p.hold_cat, 0.5, "catalyst ↑ " + t) for t, d in cats if d == 1][: p.max_cat_per_day]
    elif mode == "FADE":
        if sym and rdir and f and (f["fear_theme"] == 0 or not p.fade_greed_only): sig.append(("FADE_THEME", sym, -rdir, p.hold_theme, 1.0, p1.name))
        if len(sec.plays) > 1:
            s2, r2 = map_play(sec.plays[1].name)
            if s2 and r2 and s2 not in prev_syms and p.fade_new2: sig.append(("FADE_NEW2", s2, -r2, p.hold_theme, 0.75, sec.plays[1].name))
        for q in sec.plays[2:4]:
            s3, r3 = map_play(q.name)
            if s3 and r3 and s3 in prev_syms and p.fade_long34: sig.append(("FADE_LONG34", s3, r3, p.hold_theme, 0.5, q.name))
        if p.fade_cat_down: sig += [("FADE_CATDOWN", t, 1, p.hold_cat, 0.5, "catalyst ↓ contrarian long " + t) for t, d in cats if d == -1][: p.max_cat_per_day]
        if p.fade_sector: sig += [("FADE_SECTOR", e, -1, p.hold_sector, 0.5, "Bullish " + e) for e, v in stances.items() if v == 1]
    if not sig:
        print("Orders      : none (NEUTRAL, or no qualifying signals). Hold existing positions to their time exits."); return
    net = 0.0
    for leg, s_, side, hold, scale, name in sig:
        try:
            d = prices.daily_map(prices._fetch(s_, "1d", rdate - dt.timedelta(days=45), today))
        except Exception:
            print(f"  {leg:12s} {s_:5s} no price data, skipped"); continue
        last = max(k for k in d if k <= rdate); pc = d[last][3]; atr = prices.atr_pct(d, last + dt.timedelta(days=1))
        if atr is None or atr > p.max_atr or pc < p.min_price:
            print(f"  {leg:12s} {s_:5s} skipped (ATR {atr})"); continue
        notional = min(a.equity * p.risk_per_atr / atr, a.equity * p.max_notional) * scale; qty = int(notional / pc); net += side * notional
        print(f"  {leg:12s} {s_:5s} {'BUY ' if side>0 else 'SELL'} ~{qty} sh (~{notional:,.0f}, {notional/a.equity:.0%} eq) | ref {pc:.2f} ATR10 {atr:.2%} | stop {p.stop_atr*atr:.2%} {'below' if side>0 else 'above'} | exit close of session {hold} | {name[:40]}")
    print(f"  HEDGE        SPY {'SELL' if net>0 else 'BUY '} ~{abs(net):,.0f} notional to net zero; re-size each close. Gross cap {p.gross_cap:.0%}, daily halt {p.daily_loss_halt:.0%}, size halves past {p.dd_halve:.0%} DD.")


def pairs_plan(a):
    from retailplay import context
    from retailplay.pair_book import PairParams
    p = PairParams()
    rdate = dt.date.fromisoformat(a.date) if a.date else reports.latest_available_report()
    hist = [d for d in reports.list_archive_dates() if d <= rdate][-max(p.regime_k, 25):]
    texts = {d: reports.html_to_text(reports.fetch_report_html(d)) for d in hist}
    regs = {d: context.regime(texts[d]) for d in hist}
    mode = context.regime_series(regs, p.regime_method, k=p.regime_k)[rdate][0]
    text = texts[rdate]; sec = reports.parse_retail_section(text, rdate)
    prev_syms = {map_play(q.name)[0] for q in reports.parse_retail_section(texts[hist[-2]], hist[-2]).plays} if len(hist) > 1 else set()
    today = dt.date.today()
    spy_d = prices.daily_map(prices._fetch("SPY", "1d", rdate - dt.timedelta(days=45), today)); sess = next_session(rdate, spy_d)
    stances = context.sector_stances(text); cats = context.catalysts(text)
    print(f"Report used : {rdate}   pairs for the {sess} open   equity {a.equity:,.0f}   MODE = {mode}  (votes {[regs[d]['rate_dir'] for d in hist[-p.regime_k:]]})")
    print("Retail      : " + " | ".join(f"#{q.rank} {q.name[:30]!r}->{map_play(q.name)[0]}{'*' if map_play(q.name)[0] in prev_syms else ''}" for q in sec.plays) + "   (* persisting)")
    print("Sectors     : " + ", ".join(f"{e}:{'B' if v==1 else 'b' if v==-1 else 'm'}" for e, v in stances.items()) + "   Catalysts: " + ", ".join(f"{t}{'↑' if d>0 else '↓'}" for t, d in cats))
    s1, d1 = map_play(sec.plays[0].name); theme1 = s1 if (s1 and d1 == 1) else None
    pers34 = [map_play(q.name)[0] for q in sec.plays[2:4] if map_play(q.name)[0] and map_play(q.name)[1] == 1 and map_play(q.name)[0] in prev_syms]
    cat_dn = [t for t, d in cats if d == -1][: p.max_cat]; cat_up = [t for t, d in cats if d == 1][: p.max_cat]
    bear = [e for e, v in stances.items() if v == -1][: p.max_basket] or [e for e, v in stances.items() if v == 0][: p.max_basket]
    bull = [e for e, v in stances.items() if v == 1]
    pairs = []
    if mode == "FADE" and theme1:
        pairs += [("P_F1", [s], [theme1], p.hold_f1) for s in pers34] + [("P_F2", [t], [theme1], p.hold_f2) for t in cat_dn]
    elif mode == "MOMENTUM" and bear:
        pairs += ([("P_M1", [theme1], bear, p.hold_m1)] if theme1 else []) + [("P_M2", [e], bear, p.hold_m2) for e in bull] + [("P_M3", [t], bear, p.hold_m3) for t in cat_up]
    if not pairs:
        print("Pairs       : none today (NEUTRAL, or no #1 long theme / no Bearish-or-Mixed sector to short)."); return
    for kind, longs, shorts, hold in pairs:
        legs = []
        for syms, side in ((longs, 1), (shorts, -1)):
            for s_ in syms:
                try:
                    d = prices.daily_map(prices._fetch(s_, "1d", rdate - dt.timedelta(days=45), today))
                    last = max(k for k in d if k <= rdate); pc = d[last][3]; atr = prices.atr_pct(d, last + dt.timedelta(days=1))
                except Exception:
                    legs = None; break
                if atr is None or atr > p.max_atr or pc < p.min_price:
                    legs = None; break
                notional = min(a.equity * p.risk_per_atr / atr, a.equity * p.max_notional) / len(syms)
                legs.append((s_, side, int(notional / pc), notional, pc, atr))
            if legs is None:
                break
        if not legs:
            print(f"  {kind}: skipped (missing prices or ATR out of bounds)"); continue
        risk_unit = sum(n * atr for s_, side, q, n, pc, atr in legs if side == 1)
        print(f"  {kind}  hold {hold} sessions | pair stop: close both legs if pair loss > {p.stop_mult * risk_unit:,.0f} $ ({p.stop_mult} x long-leg ATR-dollars)")
        for s_, side, q, n, pc, atr in legs:
            print(f"      {'BUY ' if side>0 else 'SELL'} {s_:5s} ~{q} sh (~{n:,.0f}, {n/a.equity:.0%} eq) ref {pc:.2f} ATR10 {atr:.2%}")
    print(f"Rules       : max {p.max_pairs} pairs, gross cap {p.gross_cap:.0%}, daily halt {p.daily_loss_halt:.0%}, size halves past {p.dd_halve:.0%} DD; residual net hedged with SPY.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", type=float, default=100_000)
    ap.add_argument("--date", type=str, default=None, help="report date to use (default: newest available)")
    ap.add_argument("--legs", type=str, default=None)
    ap.add_argument("--weekly", action="store_true", help="print the weekly Retail #1 Fade pair instead of the intraday plan")
    ap.add_argument("--ls", action="store_true", help="print the Narrative Long/Short orders (section 10 of the README)")
    ap.add_argument("--regime", action="store_true", help="print today's regime mode and the regime-gated book orders (section 12)")
    ap.add_argument("--pairs", action="store_true", help="print today's regime mode and the long/short PAIRS it implies (section 13)")
    a = ap.parse_args()
    if a.pairs:
        return pairs_plan(a)
    if a.regime:
        return regime_plan(a)
    if a.weekly:
        return weekly_plan(a)
    if a.ls:
        return ls_plan(a)
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
