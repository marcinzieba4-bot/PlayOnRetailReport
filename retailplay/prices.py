"""Price data via Yahoo Finance chart API (no API key), cached as JSON.

Intervals used: 1d (ATR, previous close), 1h (whole backtest window),
15m (last 60 days only - Yahoo limit; used as a finer cross-check).
All timestamps are converted to America/New_York.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import subprocess
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CA = os.environ.get("RETAILPLAY_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
Bar = tuple  # (datetime_et, open, high, low, close, volume)


def _fetch(sym: str, interval: str, start: dt.date, end: dt.date, rng: str | None = None) -> list[Bar]:
    p1 = int(dt.datetime.combine(start, dt.time(), tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.combine(end + dt.timedelta(days=1), dt.time(), tzinfo=dt.timezone.utc).timestamp())
    q = f"interval={interval}&includePrePost=false&" + (f"range={rng}" if rng else f"period1={p1}&period2={p2}")
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?{q}"
    cmd = ["curl", "-s", "-A", "Mozilla/5.0", url]
    if os.path.exists(CA):
        cmd[1:1] = ["--cacert", CA]
    last = ""
    for attempt in range(4):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        last = r.stdout
        try:
            res = json.loads(r.stdout)["chart"]["result"][0]
            ts = res["timestamp"]
            qt = res["indicators"]["quote"][0]
            return [
                (dt.datetime.fromtimestamp(t, ET), qt["open"][i], qt["high"][i], qt["low"][i], qt["close"][i], qt["volume"][i])
                for i, t in enumerate(ts)
                if qt["close"][i] is not None and qt["open"][i] is not None
            ]
        except Exception:
            time.sleep(1 + attempt)
    raise RuntimeError(f"yahoo fetch failed {sym} {interval}: {last[:120]}")


def get_bars(sym: str, interval: str, start: dt.date, end: dt.date, cache_dir: str = "data/prices") -> list[Bar]:
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, f"{sym}_{interval}.json")
    if os.path.exists(p):
        rows = json.load(open(p))
        return [(dt.datetime.fromisoformat(r[0]), *r[1:]) for r in rows]
    bars = _fetch(sym, interval, start, end, rng="60d" if interval == "15m" else None)
    json.dump([(b[0].isoformat(), *b[1:]) for b in bars], open(p, "w"))
    return bars


def daily_map(bars: list[Bar]) -> dict[dt.date, tuple]:
    return {b[0].date(): b[1:] for b in bars}


def session_bars(bars: list[Bar], day: dt.date) -> list[Bar]:
    return [b for b in bars if b[0].date() == day and dt.time(9, 30) <= b[0].time() < dt.time(16, 0)]


def atr_pct(daily: dict[dt.date, tuple], asof: dt.date, n: int = 10) -> float | None:
    """Average true range over the n sessions strictly before `asof`, as a fraction of prev close."""
    ds = sorted(d for d in daily if d < asof)[-(n + 1):]
    if len(ds) < n + 1:
        return None
    trs = []
    for a, b in zip(ds[:-1], ds[1:]):
        pc = daily[a][3]
        o, h, l, c, v = daily[b][:5]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)) / pc)
    return sum(trs) / len(trs)
