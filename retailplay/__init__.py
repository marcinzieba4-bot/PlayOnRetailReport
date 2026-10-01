"""Retail-gap-fade: a short-term (intraday) strategy driven by the
"What Retail Is Playing" section of the ZembiHF daily Market Intelligence Briefing.

Point-in-time rule: the briefing dated D is published ~17:17 UTC (13:17 ET) on D.
The strategy trades the *next* US cash session (D+1) using report D only.
"""
__all__ = ["reports", "mapping", "prices", "strategy", "backtest"]
