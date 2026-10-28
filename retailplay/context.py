"""Structured signals from the rest of the briefing (beyond the retail section).

* sector stances   : the Bullish / Bearish / Mixed line under each Sector Deep Dive header
* macro stance     : the same line under the United States header
* catalysts        : $TICKER + direction arrow in High-Conviction Stock Catalysts
* retail #1 mode   : the 20-session move the report quotes for the #1 theme and dip/chase words
All are read from the report text only (point-in-time).
"""
from __future__ import annotations
import re

SECTORS = {"XLK": r"XLK", "XLC": r"XLC", "XLF": r"XLF", "XLE": r"XLE", "XLI": r"XLI", "XLY": r"XLY", "XLP": r"XLP",
           "XLV": r"XLV", "XLB": r"XLB", "XLRE": r"XLRE", "XLU": r"XLU", "SOXX": r"Semis"}
STANCE = {"bullish": 1, "bearish": -1, "mixed": 0, "neutral": 0}
CRYPTO_TICKERS = {"XRP", "BTC", "ETH", "SOL", "DOGE", "ADA", "BNB", "USDT", "USDC"}


def _block(text: str, start_rx: str) -> str:
    m = re.search(start_rx, text)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"\n## ", rest)
    return rest[: n.start()] if n else rest[:6000]


def sector_stances(text: str) -> dict[str, int]:
    out = {}
    for etf, rx in SECTORS.items():
        b = _block(text, r"## [^\n]*" + rx + r"[^\n]*\n")
        if not b:
            continue
        first = b.strip().split("\n")[0].strip().lower()
        if first in STANCE:
            out[etf] = STANCE[first]
    return out


def macro_stance(text: str) -> int | None:
    b = _block(text, r"## 🇺🇸 United States[^\n]*\n")
    if not b:
        return None
    first = b.strip().split("\n")[0].strip().lower()
    return STANCE.get(first)


def catalysts(text: str) -> list[tuple[str, int]]:
    """[(ticker, +1/-1)] from the catalysts section, in order."""
    m = re.search(r"## ⚡ High-Conviction Stock Catalysts(.*?)(?:## 🔥 What Retail|$)", text, flags=re.S)
    if not m:
        return []
    sec = m.group(1)
    out = []
    # the block for each catalyst starts with '## ' then '$TICKER' (older/newer formats) or '## $TICKER — Name — ↑ watch'
    for part in re.split(r"\n## ?", sec):
        head = part.strip()[:200]
        t = re.search(r"\$([A-Z]{1,5})(?:\.[A-Z]{1,2})?\b", head)
        if not t or t.group(1) in CRYPTO_TICKERS:
            continue
        arrow = re.search(r"[↑↓]", head[:200])
        if not arrow:
            lw = head.lower()
            d = 1 if "bullish" in lw[:200] else -1 if "bearish" in lw[:200] else 0
        else:
            d = 1 if arrow.group(0) == "↑" else -1
        if d:
            out.append((t.group(1), d))
    return out


MOVE_RX = re.compile(r"(?:up|down|↑|↓|\+|-|−)\s?(\d+(?:\.\d+)?)%\s?(?:over|vs|in)\s?(?:the\s)?(?:20|four|4|4W|20-session)", re.I)


def retail_mode(play_body: str) -> dict:
    """Quoted 20-session / 4-week move for the theme, plus dip/chase vocabulary."""
    body = play_body or ""
    moves = []
    for m in re.finditer(r"(up|down|↑|↓)\s?(\d+(?:\.\d+)?)%\s?(?:over|vs|in)\s?(?:the\s)?(?:20 sessions|20-session|four weeks|4W ago|4 weeks|20 observations|20 daily)", body, flags=re.I):
        sign = 1 if m.group(1).lower() in ("up", "↑") else -1
        moves.append(sign * float(m.group(2)))
    quoted = moves[0] if moves else None
    lw = body.lower()
    dip = len(re.findall(r"\b(dip|dips|selloff|sell-off|decline|worst day|pullback|crash|drawdown|bargain|on sale|cheaper|averaging down)\b", lw))
    chase = len(re.findall(r"\b(record|all-time high|parabolic|frenzy|mania|surge|surging|ripping|breakout|melt-up|euphoria|fomo)\b", lw))
    mode = "dip" if (quoted is not None and quoted < -5) or (quoted is None and dip > chase) else "chase" if (quoted is not None and quoted > 8) or (quoted is None and chase > dip) else "flat"
    return {"quoted_20d": quoted, "dip_words": dip, "chase_words": chase, "mode": mode}


def regime(text: str) -> dict:
    """Liquidity / rates regime read from the US macro block and the capital-flows block.

    rate_dir : -1 cut / easing bias, 0 hold or unclear, +1 hike bias (from the one-line macro subtitle + stance text)
    liq      : -1 tightening, +1 easing / returning, 0 unclear (capital-flows block vocabulary)
    y10      : quoted 10-year yield level if present
    vix      : quoted VIX level if present
    """
    us = _block(text, r"## 🇺🇸 United States[^\n]*\n")
    lines = [l.strip() for l in us.split("\n") if l.strip()]
    sub = (lines[1] if len(lines) > 1 else "").lower()
    head = (" ".join(lines[:6])).lower()
    rate = 0
    if re.search(r"hike|hiking|tighten|↑ rates|raise", sub) and not re.search(r"cut", sub):
        rate = 1
    elif re.search(r"cut|easing|ease|↓ rates|dovish", sub) and not re.search(r"hike", sub):
        rate = -1
    else:
        h = len(re.findall(r"\b(hike|hikes|hiking|tightening|hawkish)\b", head)); c = len(re.findall(r"\b(cut|cuts|cutting|easing|dovish)\b", head))
        rate = 1 if h > c else -1 if c > h else 0
    cf = _block(text, r"## 💰 Capital Flows & Liquidity[^\n]*\n")
    cf = cf + _block(text[text.find("Capital Flows") + 20:], r"## 💰 Capital Flows[^\n]*\n") if cf else cf
    cl = cf.lower()
    tight = len(re.findall(r"\b(tightening|tighten|contraction|contracting|draining|drain|receding|withdrawal|hawkish|restrictive)\b", cl))
    ease = len(re.findall(r"\b(easing|returning|expanding|expansion|injection|injecting|abundant|ample|dovish|accommodative|loosening)\b", cl))
    liq = 1 if ease > tight else -1 if tight > ease else 0
    y = re.search(r"10[- ]?(?:year|Y)[^.%\n]{0,40}?(\d\.\d{1,2})\s?%", text)
    v = re.search(r"VIX[^.\n]{0,30}?(\d{2}\.\d{1,2})", text)
    return {"rate_dir": rate, "liq": liq, "y10": float(y.group(1)) if y else None, "vix": float(v.group(1)) if v else None,
            "tight_words": tight, "ease_words": ease, "subtitle": sub[:60]}


def regime_series(regs: dict, method: str = "composite", k: int = 10, lookback: int = 60) -> dict:
    """Point-in-time regime mode per report date from the per-report `regime()` dicts.

    Nothing here uses a fixed yield level. Each date only sees reports dated <= itself.
      'text'      : majority vote of rate_dir over the last k reports (+ liquidity words as tie-break)
      'ytrend'    : sign of the change in the quoted 10Y over the last k reports (falling -> easing)
      'yrank'     : quoted 10Y vs its rolling median over `lookback` reports (below -> easing)
      'composite' : text vote + ytrend + yrank; MOMENTUM if score <= -2, FADE if score >= +2
      'fixed'     : legacy: rate_dir and absolute 10Y (4.3 / 4.6)
    Returns {date: ('MOMENTUM'|'FADE'|'NEUTRAL', score)}.
    """
    import statistics as _st
    dates = sorted(regs)
    out = {}
    ys = []
    for i, d in enumerate(dates):
        window = dates[max(0, i - k + 1): i + 1]
        votes = [regs[x]["rate_dir"] for x in window]
        liq = [regs[x]["liq"] for x in window]
        text = _st.mean(votes) + 0.5 * _st.mean(liq)
        text_s = -1 if text <= -0.34 else 1 if text >= 0.34 else 0
        y = regs[d]["y10"]
        if y is not None:
            ys.append((d, y))
        past = [v for (x, v) in ys if x <= d]
        yt = 0
        if len(past) >= k:
            delta = past[-1] - past[-k]
            yt = -1 if delta < -0.10 else 1 if delta > 0.10 else 0
        yr = 0
        hist = past[-lookback:]
        if len(hist) >= 20 and y is not None:
            med = _st.median(hist)
            yr = -1 if y < med - 0.05 else 1 if y > med + 0.05 else 0
        if method == "text":
            score = text_s * 2
        elif method == "ytrend":
            score = yt * 2
        elif method == "yrank":
            score = yr * 2
        elif method == "composite":
            score = text_s + yt + yr
        elif method == "fixed":
            rd = regs[d]["rate_dir"]
            score = 2 if (rd == 1 or (y is not None and y >= 4.6)) else -2 if (rd <= 0 and y is not None and y < 4.3) else 0
        else:
            raise ValueError(method)
        mode = "MOMENTUM" if score <= -2 else "FADE" if score >= 2 else "NEUTRAL"
        out[d] = (mode, score)
    return out
