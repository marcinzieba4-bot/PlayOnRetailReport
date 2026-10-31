"""HTML chart: lean regime book (k5/k10/k20, and unhedged k10) vs SPY, with SPY drawdown episodes shaded."""
import datetime as dt, json, os, sys, math, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retailplay import reports, prices, regime_book
from retailplay.regime_book import RegimeParams

def main(out="results/lean_vs_spy.html"):
    secs = reports.load_sections(); S = {dt.date.fromisoformat(s.date): s.plays for s in secs}
    T = {d: reports.html_to_text(open(f"data/reports/{d}.html").read()) for d in S}
    start, end = min(S) + dt.timedelta(days=1), max(S)
    spy = prices.daily_map(prices.get_bars("SPY", "1d", start - dt.timedelta(days=45), end))
    LEAN = dict(mom_theme=False, fade_new2=False, fade_long34=False)
    runs = {"lean k5": RegimeParams(**LEAN, regime_k=5), "lean k10": RegimeParams(**LEAN), "lean k20": RegimeParams(**LEAN, regime_k=20), "k10 unhedged": RegimeParams(**LEAN, hedge=False)}
    res = {k: regime_book.run(S, T, start, end, p) for k, p in runs.items()}
    dates = [d[0] for d in res["lean k10"]["daily"]]
    eq = {k: [d[3] for d in r["daily"]] for k, r in res.items()}
    d0 = dt.date.fromisoformat(dates[0]); td = sorted(spy); prev = td[td.index(d0) - 1]
    eq["SPY"] = [100000 * spy[dt.date.fromisoformat(d)][3] / spy[prev][3] for d in dates]
    def dd(series):
        pk, out = series[0], []
        for v in series: pk = max(pk, v); out.append(v / pk - 1)
        return out
    DD = {k: dd(v) for k, v in eq.items()}
    # SPY drawdown episodes >= 3%
    eps, pk, cur = [], None, None
    for i, d in enumerate(dates):
        c = eq["SPY"][i]
        if pk is None or c >= pk[1]:
            if cur and cur["dd"] <= -0.03: eps.append(cur)
            pk, cur = (i, c), None
        else:
            if cur is None: cur = {"a": pk[0], "b": i, "dd": c / pk[1] - 1}
            if c / pk[1] - 1 < cur["dd"]: cur["dd"] = c / pk[1] - 1; cur["b"] = i
    if cur and cur["dd"] <= -0.03: eps.append(cur)
    modes = res["lean k10"]["modes"]
    pos = [d[1] for d in res["lean k10"]["daily"]]; hed = [d[2] for d in res["lean k10"]["daily"]]
    W, L, R = 980, 60, 16; n = len(dates); x = lambda i: L + (W - L - R) * i / (n - 1)
    def grid(lo, hi, top, h, fmt, steps=4):
        g = []
        for k in range(steps + 1):
            v = lo + (hi - lo) * k / steps; yy = top + h - (v - lo) / (hi - lo) * h
            g.append(f'<line x1="{L}" x2="{W-R}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/><text x="{L-8}" y="{yy+4:.1f}" class="ax" text-anchor="end">{fmt(v)}</text>')
        return "".join(g)
    def xaxis(top, h):
        o = []
        for i, d in enumerate(dates):
            dd_ = dt.date.fromisoformat(d)
            if i == 0 or (dt.date.fromisoformat(dates[i-1]).month != dd_.month and dd_.month in (1, 4, 7, 10)):
                o.append(f'<text x="{x(i):.1f}" y="{top+h+18}" class="ax" text-anchor="middle">{dd_.strftime("%b %y")}</text>')
        return "".join(o)
    def shade(top, h):
        return "".join(f'<rect x="{x(e["a"]):.1f}" y="{top}" width="{max(x(e["b"])-x(e["a"]),2):.1f}" height="{h}" class="shade"/>' for e in eps)
    def modeband(y):
        o = []; cur = None
        for i, d in enumerate(dates):
            m = modes.get(d, "NEUTRAL")
            if cur is None or m != cur[0]:
                if cur: o.append(f'<rect x="{x(cur[1]):.1f}" y="{y}" width="{x(i)-x(cur[1]):.1f}" height="6" class="m{cur[0][0]}"/>')
                cur = (m, i)
        o.append(f'<rect x="{x(cur[1]):.1f}" y="{y}" width="{x(n-1)-x(cur[1]):.1f}" height="6" class="m{cur[0][0]}"/>')
        return "".join(o)
    series = ["lean k10", "lean k5", "lean k20", "k10 unhedged", "SPY"]
    # panel 1 equity
    H1, T1, B1 = 340, 20, 36; allv = [v for k in series for v in eq[k]]; lo, hi = min(allv) * 0.995, max(allv) * 1.005
    y1 = lambda v: T1 + (H1 - T1 - B1) - (v - lo) / (hi - lo) * (H1 - T1 - B1)
    lines = "".join(f'<polyline points="{" ".join(f"{x(i):.1f},{y1(v):.1f}" for i,v in enumerate(eq[k]))}" class="s{j+1}"/>' for j, k in enumerate(series))
    labels = "".join(f'<text x="{W-R-4}" y="{y1(eq[k][-1])+4:.1f}" class="lbl s{j+1}t" text-anchor="end">{k} {eq[k][-1]/1000:,.1f}k</text>' for j, k in enumerate(series))
    svg1 = f'<svg viewBox="0 0 {W} {H1}" class="chart">{shade(T1,H1-T1-B1)}{grid(lo,hi,T1,H1-T1-B1,lambda v:f"{v/1000:,.0f}k")}<line x1="{L}" x2="{W-R}" y1="{y1(100000):.1f}" y2="{y1(100000):.1f}" class="base"/>{lines}{labels}{modeband(T1+H1-T1-B1-6)}{xaxis(T1,H1-T1-B1)}</svg>'
    # panel 2 drawdowns
    H2, T2, B2 = 200, 12, 30; dlo = min(min(DD["SPY"]), min(DD["lean k10"])) * 1.1
    y2 = lambda v: T2 + (H2 - T2 - B2) - (v - dlo) / (0 - dlo) * (H2 - T2 - B2)
    svg2 = (f'<svg viewBox="0 0 {W} {H2}" class="chart">{shade(T2,H2-T2-B2)}{grid(dlo,0,T2,H2-T2-B2,lambda v:f"{v:.0%}",3)}'
            f'<polygon points="{x(0):.1f},{y2(0):.1f} {" ".join(f"{x(i):.1f},{y2(v):.1f}" for i,v in enumerate(DD["SPY"]))} {x(n-1):.1f},{y2(0):.1f}" class="spyfill"/>'
            f'<polyline points="{" ".join(f"{x(i):.1f},{y2(v):.1f}" for i,v in enumerate(DD["lean k10"]))}" class="s1"/>'
            f'<text x="{L+6}" y="{T2+14}" class="lbl">drawdown: lean k10 (line) vs SPY (area)</text>{xaxis(T2,H2-T2-B2)}</svg>')
    # panel 3 daily pnl split
    H3, T3, B3 = 200, 12, 30; tot = [a + b for a, b in zip(pos, hed)]; m = max(abs(v) for v in tot) * 1.1
    y3 = lambda v: T3 + (H3 - T3 - B3) / 2 - v / m * (H3 - T3 - B3) / 2
    bw = max((W - L - R) / n - 1, 1.2)
    bars = "".join(f'<rect x="{x(i)-bw/2:.1f}" y="{min(y3(v),y3(0)):.1f}" width="{bw:.1f}" height="{abs(y3(v)-y3(0)):.1f}" class="{"pos" if v>=0 else "neg"}"/>' for i, v in enumerate(tot))
    hl = f'<polyline points="{" ".join(f"{x(i):.1f},{y3(v):.1f}" for i,v in enumerate(hed))}" class="s2 thin"/>'
    svg3 = f'<svg viewBox="0 0 {W} {H3}" class="chart">{shade(T3,H3-T3-B3)}{grid(-m,m,T3,H3-T3-B3,lambda v:f"{v:+,.0f}",2)}{bars}{hl}<text x="{L+6}" y="{T3+14}" class="lbl">daily P&amp;L $ (bars: book) and the SPY hedge leg alone (orange line), k10</text>{xaxis(T3,H3-T3-B3)}</svg>'
    # stats table
    def stats(k):
        r = [(d[1] + d[2]) / (d[3] - d[1] - d[2]) for d in res[k]["daily"]] if k != "SPY" else [eq["SPY"][i] / eq["SPY"][i-1] - 1 for i in range(1, n)]
        sd = st.pstdev(r); return eq[k][-1] / 100000 - 1, sd * math.sqrt(252), (st.mean(r) / sd * math.sqrt(252)) if sd else 0, min(DD[k])
    rows = "".join(f'<tr><td><span class="sw s{j+1}bg"></span>{k}</td><td class="num">{t:+.1%}</td><td class="num">{v:.1%}</td><td class="num">{sh:.2f}</td><td class="num">{d:+.1%}</td></tr>' for j, k in enumerate(series) for (t, v, sh, d) in [stats(k)])
    ep_rows = "".join(f'<tr><td>{dates[e["a"]]} → {dates[e["b"]]}</td><td class="num dn">{e["dd"]:+.1%}</td>' + "".join(f'<td class="num {"up" if eq[k][e["b"]]/eq[k][e["a"]]-1>=0 else "dn"}">{eq[k][e["b"]]/eq[k][e["a"]]-1:+.2%}</td>' for k in series[:4]) + '</tr>' for e in eps)
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lean book vs SPY</title>
<style>
:root{{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--base:#c3c2b7;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#898781;--pos:#2a78d6;--neg:#e34948;--up:#006300;--dn:#d03b3b;--ring:rgba(11,11,11,.1);--shade:rgba(227,73,72,.10)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--grid:#2c2c2a;--base:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#898781;--pos:#3987e5;--neg:#e66767;--up:#0ca30c;--dn:#e66767;--ring:rgba(255,255,255,.1);--shade:rgba(230,103,103,.14)}}}}
body{{margin:0;background:var(--plane);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}} .wrap{{max-width:1020px;margin:0 auto}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:var(--ink2);margin:0 0 14px}} .card{{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:12px;margin-bottom:14px}} .card h2{{font-size:14px;margin:0 0 6px;color:var(--ink2)}}
.chart{{width:100%;height:auto;display:block}} .grid{{stroke:var(--grid)}} .base{{stroke:var(--base);stroke-dasharray:3 3}} .ax{{fill:var(--muted);font-size:11px}} .lbl{{fill:var(--ink2);font-size:11px;font-weight:600}}
.s1{{fill:none;stroke:var(--s1);stroke-width:2}} .s2{{fill:none;stroke:var(--s2);stroke-width:2}} .s3{{fill:none;stroke:var(--s3);stroke-width:2}} .s4{{fill:none;stroke:var(--s4);stroke-width:2}} .s5{{fill:none;stroke:var(--s5);stroke-width:2;stroke-dasharray:4 3}} .thin{{stroke-width:1.2}}
.s1t{{fill:var(--s1)}} .s2t{{fill:var(--s2)}} .s3t{{fill:var(--s3)}} .s4t{{fill:var(--s4)}} .s5t{{fill:var(--s5)}}
.s1bg{{background:var(--s1)}} .s2bg{{background:var(--s2)}} .s3bg{{background:var(--s3)}} .s4bg{{background:var(--s4)}} .s5bg{{background:var(--s5)}} .sw{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}}
.shade{{fill:var(--shade)}} .spyfill{{fill:var(--s5);opacity:.25}} .pos{{fill:var(--pos)}} .neg{{fill:var(--neg)}} .mM{{fill:var(--s3)}} .mN{{fill:var(--base)}} .mF{{fill:var(--neg)}}
table{{border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;width:100%}} th,td{{padding:5px 8px;border-bottom:1px solid var(--grid);text-align:left}} th{{color:var(--muted)}} td.num,th.num{{text-align:right}} .up{{color:var(--up)}} .dn{{color:var(--dn)}}
.legend{{color:var(--ink2);font-size:12px;margin-top:6px}}
</style></head><body><div class="wrap">
<h1>Lean regime book vs SPY</h1><p class="sub">{dates[0]} → {dates[-1]}, {n} sessions, $100,000 start. Red shading = SPY drawdowns of 3% or more (peak to trough). Bottom band of the equity chart = regime vote (k10): green momentum, grey neutral, red tightening. Backtest, not live.</p>
<div class="card"><h2>Equity</h2>{svg1}<div class="legend">Lean book: easing → long Bullish sectors + ↑ catalysts vs SPY; tightening → short #1 theme + long ↓ catalysts; SPY hedge to net zero at every close (except the "unhedged" line).</div></div>
<div class="card"><h2>Drawdown from peak</h2>{svg2}</div>
<div class="card"><h2>Daily P&amp;L and the hedge leg</h2>{svg3}</div>
<div class="card"><h2>Summary</h2><table><thead><tr><th>series</th><th class="num">total</th><th class="num">ann. vol</th><th class="num">Sharpe</th><th class="num">max DD</th></tr></thead><tbody>{rows}</tbody></table>
<h2 style="margin-top:14px">SPY drawdown episodes and the book over the same days</h2><table><thead><tr><th>SPY peak → trough</th><th class="num">SPY</th>{"".join(f'<th class="num">{k}</th>' for k in series[:4])}</tr></thead><tbody>{ep_rows}</tbody></table></div>
</div></body></html>'''
    open(out, "w").write(page); print("wrote", out)

if __name__ == "__main__":
    main(*sys.argv[1:])
