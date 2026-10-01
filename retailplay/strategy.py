"""Retail Gap Fade - strategy definition (all parameters fixed a priori).

Thesis
------
The briefing's last section names the trades retail is crowding into.  A crowded
retail name tends to get chased at the next open: an overnight gap in the
crowd's direction is retail extension, a gap against the crowd is a narrative
crack with trapped longs.  Both tend to mean-revert intraday, whereas index gaps
tend to continue.  We therefore FADE THE OVERNIGHT GAP in the crowded name,
intraday only, flat by the close.

Point-in-time contract
----------------------
* Report D is published ~13:17 ET on D.  We trade session D+1 (the next US
  trading day after D).  For a Friday/Saturday/Sunday report, D+1 is Monday and
  the newest of those reports is used.
* Inputs at the 9:30 ET open of D+1: report D (names, ranks, direction),
  previous close and ATR10 (both from sessions <= D), and the opening print.
  Nothing from later in session D+1 is used for the entry decision.
"""
from __future__ import annotations
import dataclasses
import datetime as dt

from .mapping import map_play


@dataclasses.dataclass(frozen=True)
class Params:
    legs: str = "extension"      # 'extension' = fade gaps in retail's direction only; 'crack' = fade gaps against retail only; 'both'
    gap_atr: float = 0.25        # min |gap| in ATR10 units to trade
    stop_atr: float = 0.60       # stop distance from entry, ATR10 units
    target_atr: float = 1.00     # cap on profit target (gap fill, capped)
    risk_per_trade: float = 0.005  # 0.5% of equity at the stop
    max_trades_per_day: int = 2  # rank-1 and rank-2 plays at most
    daily_loss_cap: float = 0.01   # stop opening new trades after -1% day
    weekly_loss_cap: float = 0.025 # stop for the week after -2.5% week
    max_atr: float = 0.06        # skip names with ATR10 > 6% (micro-cap junk)
    min_price: float = 5.0
    spy_panic_gap: float = -0.01 # if SPY gaps < -1%, skip LONG fades (crash days trend)
    slippage_bps: float = 5.0    # per side, on top of the bar price
    notional_frac: float = 0.0   # if > 0, size as fixed fraction of equity instead of risk-at-stop
    entry_time: dt.time = dt.time(9, 30)
    exit_time: dt.time = dt.time(15, 55)


@dataclasses.dataclass
class Signal:
    session: dt.date
    report_date: dt.date
    rank: int
    play: str
    symbol: str
    retail_dir: int
    prev_close: float
    open: float
    atr: float
    gap: float            # open/prev_close - 1
    side: int             # +1 long, -1 short, 0 no trade
    reason: str
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0

    def to_dict(self):
        d = dataclasses.asdict(self)
        d["session"] = self.session.isoformat()
        d["report_date"] = self.report_date.isoformat()
        return d


def build_signal(session: dt.date, report_date: dt.date, rank: int, play_name: str, symbol: str, retail_dir: int,
                 prev_close: float, open_px: float, atr: float | None, spy_gap: float | None, p: Params = Params()) -> Signal:
    gap = open_px / prev_close - 1.0
    sig = Signal(session, report_date, rank, play_name, symbol, retail_dir, prev_close, open_px, atr or float("nan"), gap, 0, "")
    if atr is None:
        sig.reason = "no ATR"; return sig
    if atr > p.max_atr:
        sig.reason = f"ATR {atr:.1%} > {p.max_atr:.0%}"; return sig
    if open_px < p.min_price:
        sig.reason = "price < min"; return sig
    if abs(gap) < p.gap_atr * atr:
        sig.reason = f"gap {gap:+.2%} < {p.gap_atr}xATR ({p.gap_atr*atr:.2%})"; return sig
    side = -1 if gap > 0 else 1   # fade the gap
    with_crowd = (gap > 0) == (retail_dir > 0)
    if p.legs == "extension" and not with_crowd:
        sig.reason = "gap against retail: crack leg disabled"; return sig
    if p.legs == "crack" and with_crowd:
        sig.reason = "gap with retail: extension leg disabled"; return sig
    if side == 1 and spy_gap is not None and spy_gap < p.spy_panic_gap:
        sig.reason = f"SPY panic gap {spy_gap:+.2%}: no long fades"; return sig
    slip = p.slippage_bps / 1e4
    entry = open_px * (1 + slip * side)
    stop = entry * (1 - side * p.stop_atr * atr)
    # target: gap fill (previous close) but no further than target_atr
    fill = prev_close
    cap = entry * (1 + side * p.target_atr * atr)
    target = min(fill, cap) if side == 1 else max(fill, cap)
    sig.side, sig.entry, sig.stop, sig.target = side, entry, stop, target
    sig.reason = "fade gap-" + ("up" if gap > 0 else "down") + (" (retail extension)" if with_crowd else " (narrative crack)")
    return sig


def plays_for_session(sections: dict[dt.date, list], session: dt.date):
    """Newest report dated strictly before `session`. Returns (report_date, plays)."""
    cands = [d for d in sections if d < session]
    if not cands:
        return None, []
    d = max(cands)
    return d, sections[d]


def position_size(equity: float, entry: float, stop: float, p: Params = Params()) -> int:
    if p.notional_frac > 0:
        return int(equity * p.notional_frac / entry)
    risk = abs(entry - stop)
    if risk <= 0:
        return 0
    return int((equity * p.risk_per_trade) / risk)
