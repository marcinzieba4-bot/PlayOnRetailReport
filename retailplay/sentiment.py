"""Sentiment / tone features extracted from a play's text (lexicon based, no model).

Features (all point-in-time, from the report text only):
  tone        : (bull - bear) / (bull + bear + 1) over the body            [-1, 1]
  warn        : count of crowding / fragility words per 100 words           (>=0)
  fear_theme  : 1 if the narrative is a fear/hedge trade (gold, oil shock, defense, short),
                0 if a greed/growth trade (AI, crypto, squeeze, rotation)
  imminent    : 1 if the "when the narrative breaks" text speaks of a scheduled / imminent trigger
  quoted_4w   : the 4-week % move the report quotes for the asset (signed), or None
"""
from __future__ import annotations
import re

BULL = r"\b(rally|rallying|ripping|surge|surging|soar|soaring|breakout|momentum|strength|support|supportive|structural|genuine|real|confirmed|durable|constructive|bullish|outperform|outperforming|tailwind|accelerat\w+|record|all-time high|vindicat\w+|winning)\b"
BEAR = r"\b(fragile|fragility|crowded|crowd|late-cycle|overbought|overextended|over-extended|extension|mania|bubble|euphoria|euphoric|parabolic|trap|trapped|unfalsifiable|dangerous|danger|froth|frothy|complacent|complacency|reversal|unwind|liquidation|squeeze|crack|cracks|collapse|crash|exhaust\w*|stall\w*|fade|fading|skeptic\w*|headwind|dilution|overshoot|sell into|selling into|roll over|rolls over)\b"
WARN = r"\b(fragile|fragility|crowded|late-cycle|overbought|overextended|over-extended|mania|bubble|euphoria|euphoric|parabolic|trap|trapped|unfalsifiable|dangerous|froth|frothy|complacent|complacency|self-reinforcing|reflexive|FOMO|zealotry|triumphalist|most dangerous)\b"
FEAR = r"gold|silver|precious|oil|crude|energy|hormuz|defen[cs]e|short |bear|put trade|hedge|crisis|safe.?haven|treasur|bond|dividend|fortress|defensive|value|stagflation|uranium|nuclear|copper"
IMMINENT = r"\b(imminent|this week|next week|tomorrow|tonight|today|coming week|upcoming|due (on|this|next)|scheduled|earnings (on|night|report|season)|jobs report|CPI|PCE|FOMC|Fed (meeting|decision)|late (July|August|September|October)|mid-(July|August|September|October))\b"


def features(play: dict) -> dict:
    body = " ".join(str(play.get(k, "")) for k in ("tagline", "why", "smart_money", "breaks", "body")) if isinstance(play, dict) else ""
    words = max(len(body.split()), 1)
    bull = len(re.findall(BULL, body, flags=re.I))
    bear = len(re.findall(BEAR, body, flags=re.I))
    warn = len(re.findall(WARN, body, flags=re.I))
    name = play.get("name", "")
    fear = 1 if re.search(FEAR, name, flags=re.I) else 0
    imminent = 1 if re.search(IMMINENT, str(play.get("breaks", "")), flags=re.I) else 0
    m = re.search(r"([↑↓])\s?(\d+(?:\.\d+)?)%\s?(?:vs|over|in)\s?(?:4W|four weeks|4 weeks)", body)
    quoted = (1 if m.group(1) == "↑" else -1) * float(m.group(2)) if m else None
    return {"tone": (bull - bear) / (bull + bear + 1), "bull": bull, "bear": bear, "warn": warn / words * 100,
            "fear_theme": fear, "imminent": imminent, "quoted_4w": quoted, "words": words}
