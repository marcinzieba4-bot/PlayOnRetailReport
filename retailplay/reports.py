"""Fetch and parse the ZembiHF daily briefing archive.

Timing facts (verified from HTTP Last-Modified on all 98 archived reports,
2026-06-25 .. 2026-09-30): every report dated D is published between 17:16 and
17:18 UTC on D, i.e. ~13:17 ET, during the US cash session.  A strategy that
"uses only available data" may therefore use report D no earlier than 13:20 ET
on D; this package only uses it for the next session (D+1).
"""
from __future__ import annotations
import datetime as dt
import html as html_mod
import json
import os
import re
import subprocess
from dataclasses import dataclass, asdict, field

BASE = "https://zembihf.xyz/reports"
CA = os.environ.get("RETAILPLAY_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
PUBLISH_UTC = dt.time(17, 20)  # conservative "available after" time


def _curl(url: str) -> str:
    cmd = ["curl", "-sS", "-L", url]
    if os.path.exists(CA):
        cmd[1:1] = ["--cacert", CA]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {r.stderr[:200]}")
    return r.stdout


def list_archive_dates() -> list[dt.date]:
    idx = _curl(f"{BASE}/index.html")
    dates = re.findall(r'href="archive/(\d{4}-\d{2}-\d{2})\.html"', idx)
    return sorted({dt.date.fromisoformat(d) for d in dates})


def fetch_report_html(d: dt.date, cache_dir: str = "data/reports") -> str:
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, f"{d.isoformat()}.html")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    s = _curl(f"{BASE}/archive/{d.isoformat()}.html")
    if "What Retail Is Playing" not in s:
        raise RuntimeError(f"report {d} missing retail section (not published yet?)")
    open(p, "w", encoding="utf-8").write(s)
    return s


def html_to_text(s: str) -> str:
    t = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<(h[1-4])[^>]*>", r"\n\n## ", t)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = html_mod.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t


@dataclass
class Play:
    rank: int
    name: str
    tagline: str
    why: str = ""
    smart_money: str = ""
    breaks: str = ""


@dataclass
class RetailSection:
    date: str
    plays: list[Play] = field(default_factory=list)

    def to_dict(self):
        return {"date": self.date, "plays": [asdict(p) for p in self.plays]}


_FIELD = {
    "why": "Why retail is here",
    "smart_money": "Smart money view",
    "breaks": "When the narrative breaks",
}


def parse_retail_section(text: str, date: dt.date) -> RetailSection:
    m = re.search(r"## 🔥 What Retail Is Playing\n[^\n]*\n(.*?)(?:\nPowered by|$)", text, flags=re.S)
    sec = m.group(1) if m else ""
    out = RetailSection(date=date.isoformat())
    for part in re.split(r"\n?## ", sec):
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n")
        name = lines[0].strip()
        tag = lines[1].strip().strip('"') if len(lines) > 1 else ""
        body = "\n".join(lines[2:])
        p = Play(rank=len(out.plays) + 1, name=name, tagline=tag)
        for k, label in _FIELD.items():
            mm = re.search(label + r":\n ?(.*?)(?=\n[A-Z][^\n]{3,40}:\n|\Z)", body, flags=re.S)
            if mm:
                setattr(p, k, mm.group(1).strip())
        out.plays.append(p)
    return out


def load_sections(dates: list[dt.date] | None = None, cache_dir: str = "data/reports") -> list[RetailSection]:
    dates = dates or list_archive_dates()
    return [parse_retail_section(html_to_text(fetch_report_html(d, cache_dir)), d) for d in dates]


def latest_available_report(now_utc: dt.datetime | None = None) -> dt.date:
    """Date of the newest report that is guaranteed published at `now_utc`."""
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    d = now_utc.date()
    if now_utc.time() < PUBLISH_UTC:
        d -= dt.timedelta(days=1)
    return d


if __name__ == "__main__":
    secs = load_sections()
    json.dump([s.to_dict() for s in secs], open("data/retail_plays.json", "w"), indent=1)
    for s in secs:
        print(s.date, " | ".join(p.name for p in s.plays))
