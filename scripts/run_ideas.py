"""Improvement-idea tests on the five-year archive (README section 19): SPY risk filter, momentum-only variants, sector cross-section, breadth mood index."""
import datetime as dt, json, math, statistics as st
from collections import defaultdict
from retailplay import reports, prices, regime_book, context, lean_regime_vote as lrv
from retailplay.book import risk_report
S,T=lrv.load_archive(); start,end=min(S)+dt.timedelta(days=1),max(S)
spy=prices.daily_map(prices.get_bars('SPY','1d',start-dt.timedelta(days=45),end)); td=sorted(d for d in spy if start<=d<=end)
REG={d:context.regime(T[d]) for d in S}; MODE={d:m for d,(m,sc) in context.regime_series(REG,'text',10).items()}
SEC={d:context.sector_stances(T[d]) for d in S}
def mode_for_session(Tn):
    c=[d for d in S if d<Tn and (Tn-d).days<=3]
    return MODE[max(c)] if c else 'NONE'
YEARS=[(f'{y}-01-01',f'{y+1}-01-01',str(y)) for y in range(2022,2027)]
def yearly(rets):  # dict date->ret
    out=[]
    for a,b,l in YEARS:
        r=[v for d,v in rets.items() if a<=str(d)<b]; out.append(f"{l} {math.prod(1+x for x in r)-1:+6.1%}" if r else f"{l} n/a")
    return ' | '.join(out)
def stats(rets,lbl):
    r=list(rets.values()); m=st.mean(r); sd=st.pstdev(r); eq=1; pk=1; mdd=0
    for v in r: eq*=1+v; pk=max(pk,eq); mdd=min(mdd,eq/pk-1)
    print(f"{lbl:46s} total {eq-1:+7.1%} vol {sd*math.sqrt(252):5.1%} sharpe {m/sd*math.sqrt(252) if sd else 0:5.2f} mdd {mdd:+6.1%}  {yearly(rets)}")
print('=== A. regime as a risk filter on SPY (long SPY except when the vote says FADE) ===')
sr={d:spy[d][3]/spy[td[i-1]][3]-1 for i,d in enumerate(td) if i>0}
stats(sr,'SPY buy & hold')
stats({d:(v if mode_for_session(d)!='FADE' else 0.0) for d,v in sr.items()},'SPY, cash in FADE')
stats({d:(v if mode_for_session(d)=='MOMENTUM' else 0.0) for d,v in sr.items()},'SPY only in MOMENTUM')
stats({d:(v if mode_for_session(d) in ('MOMENTUM','NEUTRAL') else -v*0.5) for d,v in sr.items()},'SPY, half short in FADE')
print('\n=== B. lean book variants ===')
for lbl,p in [('frozen v1.0',lrv.LeanParams()),('momentum legs in MOMENTUM+NEUTRAL, cash in FADE',lrv.LeanParams(neutral_as='MOMENTUM',fade_theme=False,fade_cat_down=False)),
              ('momentum legs in MOMENTUM only, cash otherwise',lrv.LeanParams(fade_theme=False,fade_cat_down=False)),('sectors only, MOMENTUM+NEUTRAL, no stops',lrv.LeanParams(neutral_as='MOMENTUM',fade_theme=False,fade_cat_down=False,mom_cat=False,stop_atr=99)),
              ('cat↑ only, MOMENTUM+NEUTRAL',lrv.LeanParams(neutral_as='MOMENTUM',fade_theme=False,fade_cat_down=False,mom_sector=False)),('frozen, stops 3 ATR',lrv.LeanParams(stop_atr=3.0)),
              ('frozen + sector trend filter (see C)',None)]:
    if p is None: continue
    res=regime_book.run(S,T,start,end,p); r=risk_report(res,spy)
    rets={dt.date.fromisoformat(d[0]):(d[1]+d[2])/(d[3]-d[1]-d[2]) for d in res['daily']}
    print(f"{lbl:46s} total {r['total_return']:+7.1%} vol {r['ann_vol']:5.1%} sharpe {r['sharpe']:5.2f} mdd {r['max_drawdown']:+6.1%}  {yearly(rets)}  trades {r['trades']}")
print('\n=== C. sector stances as a cross-section: long Bullish / short Bearish ETFs, equal weight, 10-session hold, no regime ===')
D={}
def dm(s):
    if s not in D:
        try: D[s]=prices.daily_map(prices.get_bars(s,'1d',start-dt.timedelta(days=45),end))
        except Exception: D[s]={}
    return D[s]
def fwd(sym,R,h):
    Tn=next((t for t in td if t>R),None); d=dm(sym)
    if Tn is None: return None
    i=td.index(Tn)
    if i+h>=len(td) or Tn not in d or td[i+h] not in d: return None
    return d[td[i+h]][3]/d[Tn][0]-1
for mode in ('ALL','MOMENTUM','NEUTRAL','FADE'):
    for h in (5,10,20):
        xs=[]
        for R in sorted(S):
            if mode!='ALL' and MODE[R]!=mode: continue
            b=[fwd(e,R,h) for e,v in SEC[R].items() if v==1]; s_=[fwd(e,R,h) for e,v in SEC[R].items() if v==-1]
            b=[x for x in b if x is not None]; s_=[x for x in s_ if x is not None]
            if b and s_: xs.append(st.mean(b)-st.mean(s_))
        if len(xs)>10: print(f"  {mode:9s} {h:2d}d: n={len(xs):4d} mean={st.mean(xs)*1e4:+6.0f}bp hit={sum(x>0 for x in xs)/len(xs):.2f} t={st.mean(xs)/(st.pstdev(xs)/math.sqrt(len(xs))):+.2f}")
print('--- by year, 10d, all regimes:')
for a,b,l in YEARS:
    xs=[]
    for R in sorted(S):
        if not (a<=str(R)<b): continue
        bb=[x for x in (fwd(e,R,10) for e,v in SEC[R].items() if v==1) if x is not None]; ss=[x for x in (fwd(e,R,10) for e,v in SEC[R].items() if v==-1) if x is not None]
        if bb and ss: xs.append(st.mean(bb)-st.mean(ss))
    if xs: print(f"  {l}: n={len(xs):3d} mean={st.mean(xs)*1e4:+6.0f}bp hit={sum(x>0 for x in xs)/len(xs):.2f}")
print('\n=== D. sector breadth as a mood index: (#Bullish - #Bearish) sectors -> SPY next 10 sessions ===')
rows=[]
for R in sorted(S):
    v=SEC[R]; br=sum(1 for x in v.values() if x==1)-sum(1 for x in v.values() if x==-1); f=fwd('SPY',R,10)
    if f is not None: rows.append((br,f))
for lo,hi,l in [(-99,-3,'breadth <= -3'),(-2,2,'-2..+2'),(3,99,'breadth >= +3')]:
    xs=[f for br,f in rows if lo<=br<=hi]
    if xs: print(f"  {l:16s} n={len(xs):4d} SPY 10d mean={st.mean(xs)*1e4:+6.0f}bp hit={sum(x>0 for x in xs)/len(xs):.2f}")
