"""Map a free-text retail play name to a liquid, exchange-traded proxy.

Returns (ticker, direction): direction +1 = retail is long the theme,
-1 = retail is short/bearish the theme, 0 = untradeable (event/vol plays).
Crypto themes map to IBIT so that everything trades in the US cash session.
Rules are ordered: first match wins.
"""
import re
# (regex on play name, ticker, direction) direction: +1 long, -1 short (retail is short / bearish)
RULES=[
 (r'short gold|long dust','GLD',-1),
 (r'short bitcoin|bitcoin short|bearish crypto|crypto skepticism','IBIT',-1),
 (r'short.*bond|bear bond|yields to 6','TLT',-1),
 (r'ai short|short ai|nvidia put|bubble pop|ai skepticism|short big tech|tech top|ai bubble|neocloud short','QQQ',-1),
 (r'long-duration treasur','TLT',1),
 (r'bitcoin|btc','IBIT',1),
 (r'xrp|solana|aave|rave\.x|hbar|atom\.x','IBIT',1),
 (r'crypto','IBIT',1),
 (r'gold|precious|xau','GLD',1),
 (r'silver|agq','SLV',1),
 (r'copper|mining|strategic.*metals','COPX',1),
 (r'oil|energy|crude|hormuz|refiner|xle','XLE',1),
 (r'nuclear|uranium|smr','URA',1),
 (r'small.?cap|russell|rotation|breadth|everything except','IWM',1),
 (r'nvidia|nvda','NVDA',1),
 (r'micron|\bmu\b|memory|hbm|sandisk|sk hynix|korean|samsung','MU',1),
 (r'\bamd\b','AMD',1),
 (r'semiconductor equipment|lrcx','LRCX',1),
 (r'optics|lumentum','LITE',1),
 (r'tsmc|taiwan semi|\btsm\b','TSM',1),
 (r'semi|chip|soxl','SMH',1),
 (r'tesla|tsla','TSLA',1),(r'apple|aapl','AAPL',1),(r'microsoft|msft','MSFT',1),(r'palantir|pltr','PLTR',1),
 (r'oracle|orcl','ORCL',1),(r'servicenow','NOW',1),(r'sofi','SOFI',1),(r'paypal','PYPL',1),(r'amazon|amzn','AMZN',1),
 (r'\bmeta\b','META',1),(r'hyperscaler','QQQ',1),
 (r'spacex|space|starship','RKLB',1),
 (r'wendy|wen\b','WEN',1),(r'blackberry|\bbb\b','BB',1),(r'\bsls\b|sellas','SLS',1),(r'asts','ASTS',1),(r'ondas|onds','ONDS',1),
 (r'cannabis','MSOS',1),(r'defen[cs]e|raytheon|\brtx\b','ITA',1),(r'abbv','ABBV',1),(r'\bdjt\b','DJT',1),(r'grpn','GRPN',1),
 (r'circle|crcl','CRCL',1),(r'amc','AMC',1),(r'take-two|ttwo|gta','TTWO',1),(r'biotech|insmed','XBI',1),(r'cyber','CIBR',1),
 (r'nbis|nebius','NBIS',1),(r'reddit|rddt','RDDT',1),(r'nike|nke','NKE',1),(r'moderna|mrna','MRNA',1),(r'glp-1|weight-loss|lilly','LLY',1),
 (r'berkshire|buffett','BRK-B',1),(r'jpmorgan|\bjpm\b|big bank|financials','XLF',1),(r'u\.s\. steel|tariff','SLX',1),(r'fngr','FNGR',1),
 (r'japan|nikkei','EWJ',1),(r'china','FXI',1),(r'european|europe|uk','VGK',1),(r'international|non-us|rest of world','VEU',1),
 (r'dividend|fortress|value|stagflation-proof|defensive','RSP',1),(r'ai|mega-cap|nasdaq|big tech|tech earnings|s&p|broad market|buy the dip|leveraged long|buy everything','QQQ',1),
 (r'pershing|ackman','PSHZF',1),(r'prediction','DKNG',1),(r'fed|rate hike|rate-cut|volatility','SPY',0),(r'trump','DJT',1),(r'take-private|buyout','SPY',0),
]
def map_play(name):
    n=name.lower()
    for rx,t,d in RULES:
        if re.search(rx,n): return t,d
    return None,0
