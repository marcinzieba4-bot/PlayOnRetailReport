"""Render an HTML P&L report (equity curve, daily P&L, drawdown, trade table) for one results file."""
import datetime as dt, json, os, sys, html
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main(path="results/LS_base.json", out="results/LS_base_report.html"):
    res = json.load(open(path)); dl = res["daily"]; tr = sorted(res["trades"], key=lambda t: (t["entry_day"], t["sym"]))
    eq0 = res["equity0"]
    dates = [d[0] for d in dl]; eq = [d[3] for d in dl]; pnl = [d[1] + d[2] for d in dl]
    peak, dd = eq0, []
    for e in eq:
        peak = max(peak, e); dd.append(e / peak - 1)
    W, H, L, R, T, B = 960, 260, 56, 16, 18, 28
    n = len(dates); x = lambda i: L + (W - L - R) * i / max(n - 1, 1)
    def yscale(vals, h, top, pad=0.06):
        lo, hi = min(vals), max(vals); span = (hi - lo) or 1; lo -= span * pad; hi += span * pad
        return (lambda v: top + h - (v - lo) / (hi - lo) * h), lo, hi
    def grid(ylo, yhi, top, h, fmt, steps=4):
        g = []
        for k in range(steps + 1):
            v = ylo + (yhi - ylo) * k / steps; yy = top + h - (v - ylo) / (yhi - ylo) * h
            g.append(f'<line x1="{L}" x2="{W-R}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/><text x="{L-8}" y="{yy+4:.1f}" class="ax" text-anchor="end">{fmt(v)}</text>')
        return "".join(g)
    def xaxis(top, h):
        out = []
        for i, d in enumerate(dates):
            dd_ = dt.date.fromisoformat(d)
            if dd_.day <= 7 and (i == 0 or dt.date.fromisoformat(dates[i-1]).month != dd_.month):
                out.append(f'<text x="{x(i):.1f}" y="{top+h+18}" class="ax" text-anchor="middle">{dd_.strftime("%b %Y")}</text>')
        return "".join(out)
    # equity curve
    ye, lo, hi = yscale(eq, H - T - B, T)
    pts = " ".join(f"{x(i):.1f},{ye(v):.1f}" for i, v in enumerate(eq))
    svg_eq = (f'<svg viewBox="0 0 {W} {H}" class="chart" data-kind="line">{grid(lo,hi,T,H-T-B,lambda v:f"{v:,.0f}")}'
              f'<line x1="{L}" x2="{W-R}" y1="{ye(eq0):.1f}" y2="{ye(eq0):.1f}" class="base"/>'
              f'<polyline points="{pts}" class="s1"/>'
              f'<circle cx="{x(n-1):.1f}" cy="{ye(eq[-1]):.1f}" r="4" class="s1dot"/><text x="{x(n-1)-8:.1f}" y="{ye(eq[-1])-10:.1f}" class="lbl" text-anchor="end">{eq[-1]:,.0f} ({eq[-1]/eq0-1:+.2%})</text>'
              f'{xaxis(T,H-T-B)}<g class="hover"></g></svg>')
    # daily pnl bars
    yp, plo, phi = yscale(pnl + [0], H - T - B, T)
    bw = max((W - L - R) / n - 2, 2)
    bars = "".join(f'<rect x="{x(i)-bw/2:.1f}" y="{min(yp(v),yp(0)):.1f}" width="{bw:.1f}" height="{abs(yp(v)-yp(0)):.1f}" class="{"pos" if v>=0 else "neg"}" rx="2"/>' for i, v in enumerate(pnl))
    svg_pnl = (f'<svg viewBox="0 0 {W} {H}" class="chart" data-kind="bar">{grid(plo,phi,T,H-T-B,lambda v:f"{v:+,.0f}")}'
               f'<line x1="{L}" x2="{W-R}" y1="{yp(0):.1f}" y2="{yp(0):.1f}" class="base"/>{bars}{xaxis(T,H-T-B)}<g class="hover"></g></svg>')
    # drawdown area
    yd, dlo, dhi = yscale(dd + [0], 120, T, 0.1)
    apts = " ".join(f"{x(i):.1f},{yd(v):.1f}" for i, v in enumerate(dd))
    svg_dd = (f'<svg viewBox="0 0 {W} {160}" class="chart" data-kind="area">{grid(dlo,0,T,120,lambda v:f"{v:.1%}",2)}'
              f'<polygon points="{x(0):.1f},{yd(0):.1f} {apts} {x(n-1):.1f},{yd(0):.1f}" class="ddfill"/><polyline points="{apts}" class="ddline"/>'
              f'<text x="{x(dd.index(min(dd))):.1f}" y="{yd(min(dd))+14:.1f}" class="lbl" text-anchor="middle">max DD {min(dd):.2%}</text>{xaxis(T,120)}<g class="hover"></g></svg>')
    # stats
    import statistics as st, math
    rets = [(d[1] + d[2]) / (d[3] - d[1] - d[2]) for d in dl]
    sharpe = st.mean(rets) / st.pstdev(rets) * math.sqrt(252)
    wins = [t for t in tr if t["ret"] > 0]
    tiles = [("Final equity", f"{eq[-1]:,.0f}"), ("Total return", f"{eq[-1]/eq0-1:+.2%}"), ("Sharpe (ann.)", f"{sharpe:.2f}"), ("Max drawdown", f"{min(dd):.2%}"),
             ("Worst day", f"{min(pnl)/eq0:+.2%}"), ("Trades / stops", f"{len(tr)} / {sum(t['exit_reason']=='stop' for t in tr)}"), ("Trade hit rate", f"{len(wins)/len(tr):.0%}")]
    tiles_html = "".join(f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in tiles)
    rows = "".join(f'<tr><td>{i+1}</td><td>{t["entry_day"]}</td><td>{t["exit_day"]}</td><td>{t["leg"]}</td><td>{html.escape(t["play"][:48])}</td><td>{t["sym"]}</td><td>{"SHORT" if t["side"]<0 else "LONG"}</td>'
                   f'<td class="num">{t["qty"]}</td><td class="num">{t["entry"]:.2f}</td><td class="num">{t["stop"]:.2f}</td><td class="num">{t["exit"]:.2f}</td><td>{t["exit_reason"]}</td>'
                   f'<td class="num {"up" if t["ret"]>0 else "dn"}">{t["ret"]*100:+.2f}%</td><td class="num {"up" if t["ret"]>0 else "dn"}">{(t["exit"]/t["entry"]-1)*t["side"]*t["qty"]*t["entry"]:+,.0f}</td></tr>' for i, t in enumerate(tr))
    data_js = json.dumps({"dates": dates, "eq": eq, "pnl": pnl, "dd": dd, "eq0": eq0})
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Narrative L/S P&L</title>
<style>
:root{{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--base:#c3c2b7;--s1:#2a78d6;--pos:#2a78d6;--neg:#e34948;--up:#006300;--dn:#d03b3b;--ring:rgba(11,11,11,.1)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--base:#383835;--s1:#3987e5;--pos:#3987e5;--neg:#e66767;--up:#0ca30c;--dn:#e66767;--ring:rgba(255,255,255,.1)}}}}
:root[data-theme="dark"]{{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--base:#383835;--s1:#3987e5;--pos:#3987e5;--neg:#e66767;--up:#0ca30c;--dn:#e66767;--ring:rgba(255,255,255,.1)}}
body{{margin:0;background:var(--plane);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}}
.wrap{{max-width:1000px;margin:0 auto}} h1{{font-size:20px;margin:0 0 4px}} .sub{{color:var(--ink2);margin:0 0 16px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:16px}}
.tile{{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:10px 12px}} .tile .k{{color:var(--muted);font-size:12px}} .tile .v{{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums}}
.card{{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:12px;margin-bottom:16px;position:relative}} .card h2{{font-size:14px;margin:0 0 6px;color:var(--ink2);font-weight:600}}
.chart{{width:100%;height:auto;display:block}} .grid{{stroke:var(--grid);stroke-width:1}} .base{{stroke:var(--base);stroke-width:1;stroke-dasharray:3 3}}
.ax{{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}} .lbl{{fill:var(--ink2);font-size:11px;font-weight:600}}
.s1{{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round}} .s1dot{{fill:var(--s1);stroke:var(--surface);stroke-width:2}}
.pos{{fill:var(--pos)}} .neg{{fill:var(--neg)}} .ddfill{{fill:var(--neg);opacity:.18}} .ddline{{fill:none;stroke:var(--neg);stroke-width:2}}
.tip{{position:absolute;pointer-events:none;background:var(--ink);color:var(--surface);font-size:12px;padding:6px 8px;border-radius:6px;display:none;white-space:nowrap;font-variant-numeric:tabular-nums}}
.xl{{stroke:var(--muted);stroke-width:1;stroke-dasharray:2 2}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums}} th,td{{padding:5px 6px;border-bottom:1px solid var(--grid);text-align:left;white-space:nowrap}} th{{color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--surface)}}
td.num,th.num{{text-align:right}} .up{{color:var(--up)}} .dn{{color:var(--dn)}} .tablewrap{{overflow:auto;max-height:70vh}}
</style></head><body><div class="wrap">
<h1>Narrative Long/Short — P&L report (LS_base)</h1>
<p class="sub">Short the #1 retail theme (greed full size, fear half), long persisting #2–#4 themes, SPY-hedged, vol-sized, 1.5 ATR stops, 5-session hold. {dates[0]} → {dates[-1]}, {n} sessions, $100,000 start. Backtest, not live.</p>
<div class="tiles">{tiles_html}</div>
<div class="card"><h2>Equity curve</h2>{svg_eq}<div class="tip"></div></div>
<div class="card"><h2>Daily P&L (positions + hedge), $</h2>{svg_pnl}<div class="tip"></div></div>
<div class="card"><h2>Drawdown from peak</h2>{svg_dd}<div class="tip"></div></div>
<div class="card"><h2>Trades ({len(tr)})</h2><div class="tablewrap"><table><thead><tr><th>#</th><th>Entry</th><th>Exit</th><th>Leg</th><th>Theme (from report)</th><th>Sym</th><th>Side</th><th class="num">Qty</th><th class="num">Entry</th><th class="num">Stop</th><th class="num">Exit</th><th>Why</th><th class="num">Ret</th><th class="num">P&L $</th></tr></thead><tbody>{rows}</tbody></table></div></div>
</div>
<script>
const D={data_js};const L={L},R={R},W={W};
document.querySelectorAll('.card').forEach(card=>{{const svg=card.querySelector('svg');if(!svg)return;const tip=card.querySelector('.tip');const g=svg.querySelector('.hover');const kind=svg.dataset.kind;
svg.addEventListener('mousemove',e=>{{const r=svg.getBoundingClientRect();const px=(e.clientX-r.left)/r.width*W;const n=D.dates.length;let i=Math.round((px-L)/(W-L-R)*(n-1));i=Math.max(0,Math.min(n-1,i));const x=L+(W-L-R)*i/Math.max(n-1,1);
g.innerHTML=`<line class="xl" x1="${{x}}" x2="${{x}}" y1="0" y2="${{svg.viewBox.baseVal.height}}"/>`;
const v=kind==='line'?`equity ${{D.eq[i].toLocaleString(undefined,{{maximumFractionDigits:0}})}} (${{((D.eq[i]/D.eq0-1)*100).toFixed(2)}}%)`:kind==='bar'?`P&L ${{D.pnl[i]>=0?'+':''}}${{D.pnl[i].toFixed(0)}} $`:`drawdown ${{(D.dd[i]*100).toFixed(2)}}%`;
tip.textContent=`${{D.dates[i]}} · ${{v}}`;tip.style.display='block';tip.style.left=Math.min(e.clientX-r.left+12,r.width-160)+'px';tip.style.top=(e.clientY-r.top-30)+'px';}});
svg.addEventListener('mouseleave',()=>{{g.innerHTML='';tip.style.display='none';}});}});
</script></body></html>'''
    open(out, "w").write(page)
    print(f"wrote {out}")
    print(f"\n{'#':>2} {'entry':10s} {'exit':10s} {'leg':3s} {'sym':5s} {'side':5s} {'qty':>5s} {'entry':>8s} {'stop':>8s} {'exit':>8s} {'why':5s} {'ret':>7s} {'pnl$':>7s}  theme")
    for i, t in enumerate(tr):
        print(f"{i+1:2d} {t['entry_day']} {t['exit_day']} {t['leg']:3s} {t['sym']:5s} {'SHORT' if t['side']<0 else 'LONG ':5s} {t['qty']:5d} {t['entry']:8.2f} {t['stop']:8.2f} {t['exit']:8.2f} {t['exit_reason']:5s} {t['ret']*100:+6.2f}% {(t['exit']/t['entry']-1)*t['side']*t['qty']*t['entry']:+7.0f}  {t['play'][:45]}")

if __name__ == "__main__":
    main(*sys.argv[1:])
