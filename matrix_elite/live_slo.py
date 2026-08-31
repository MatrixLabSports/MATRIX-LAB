from __future__ import annotations
from dataclasses import dataclass
from statistics import median
from typing import Sequence

@dataclass(frozen=True)
class LiveTiming:
    event_to_provider_ms: float
    provider_to_ingest_ms: float
    ingest_to_normalize_ms: float
    normalize_to_feature_ms: float
    feature_to_inference_ms: float
    inference_to_market_ms: float
    market_to_signal_ms: float
    signal_to_visible_ms: float
    entry_window_remaining_ms: float

    @property
    def end_to_end_ms(self):
        vals=(self.event_to_provider_ms,self.provider_to_ingest_ms,self.ingest_to_normalize_ms,
              self.normalize_to_feature_ms,self.feature_to_inference_ms,self.inference_to_market_ms,
              self.market_to_signal_ms,self.signal_to_visible_ms)
        if any(v < 0 for v in vals): raise ValueError("NEGATIVE_LATENCY")
        return sum(vals)


def _pct(values, q):
    vals=sorted(float(x) for x in values)
    if not vals: raise ValueError("EMPTY_LATENCY_SERIES")
    if len(vals)==1: return vals[0]
    pos=(len(vals)-1)*q
    lo=int(pos); hi=min(lo+1,len(vals)-1); frac=pos-lo
    return vals[lo]*(1-frac)+vals[hi]*frac

def live_slo_report(samples: Sequence[LiveTiming], *, stale_threshold_ms: float) -> dict[str,float]:
    if not samples: raise ValueError("EMPTY_LATENCY_SERIES")
    e2e=[s.end_to_end_ms for s in samples]
    return {
        "p50_ms": _pct(e2e,0.50),
        "p95_ms": _pct(e2e,0.95),
        "p99_ms": _pct(e2e,0.99),
        "missed_window_rate": sum(s.end_to_end_ms > s.entry_window_remaining_ms for s in samples)/len(samples),
        "stale_signal_rate": sum(s.end_to_end_ms > stale_threshold_ms for s in samples)/len(samples),
        "decision_too_late_rate": sum(s.entry_window_remaining_ms <= 0 for s in samples)/len(samples),
    }
