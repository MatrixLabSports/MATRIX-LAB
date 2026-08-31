from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
import json


def _canon(value) -> bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")

@dataclass(frozen=True)
class FrozenDecision:
    decision_id: str
    sport: str
    event_id: str
    market_id: str
    selection_id: str
    decided_at: datetime
    event_start_at: datetime
    decimal_odds: float | None
    matrix_probability: float | None
    action: str
    model_version: str
    feature_version: str
    odds_snapshot_sha256: str | None
    previous_record_sha256: str | None = None

    def payload(self):
        if self.sport not in {"football","tennis"}: raise ValueError("SPORT_BOUNDARY_VIOLATION")
        if self.action not in {"NO_BET","WATCH","CANDIDATE","PAPER_BET"}: raise ValueError("PAPER_ACTION_INVALID")
        if self.decided_at.tzinfo is None or self.event_start_at.tzinfo is None: raise ValueError("TIMEZONE_AWARE_REQUIRED")
        if self.decided_at >= self.event_start_at: raise ValueError("DECISION_NOT_PRE_EVENT")
        if self.decimal_odds is not None and self.decimal_odds <= 1: raise ValueError("ODDS_INVALID")
        if self.matrix_probability is not None and not 0 <= self.matrix_probability <= 1: raise ValueError("PROBABILITY_INVALID")
        d=asdict(self)
        d["decided_at"]=self.decided_at.astimezone(timezone.utc).isoformat()
        d["event_start_at"]=self.event_start_at.astimezone(timezone.utc).isoformat()
        return d

    def sha256(self) -> str:
        return sha256(_canon(self.payload())).hexdigest()

class HashChainedPaperLedger:
    def __init__(self): self._records=[]
    def append(self, decision: FrozenDecision) -> str:
        expected=self._records[-1][1] if self._records else None
        if decision.previous_record_sha256 != expected:
            raise ValueError("PAPER_LEDGER_CHAIN_MISMATCH")
        digest=decision.sha256()
        self._records.append((decision,digest))
        return digest
    @property
    def size(self): return len(self._records)
