from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping


GENESIS_HASH = "0" * 64


def _aware(value: str, *, name: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _positive(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name}_MUST_BE_POSITIVE")
    return number


def _probability(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{name}_OUT_OF_RANGE")
    return number


def _sha(value: str, *, name: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{name}_INVALID_SHA256")
    return text


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def full_kelly_fraction(p_matrix: float, entry_odds: float) -> float:
    p = _probability("P_MATRIX", p_matrix)
    odds = _positive("ENTRY_ODDS", entry_odds)
    b = odds - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (p * odds - 1.0) / b)


@dataclass(frozen=True)
class PaperSizingDecision:
    fixture_id: str
    market_key: str
    selection_key: str
    bankroll_before: float
    p_matrix: float
    entry_odds: float
    frozen_at_utc: str
    clv_state_sha256: str
    clv_closing_observations: int
    requested_fractional_kelly: float
    full_kelly_fraction: float
    applied_bankroll_fraction: float
    stake_calculated: float
    status: str
    justification: str
    mode: str = "PAPER_ONLY"
    real_money: str = "BLOCKED"

    def __post_init__(self) -> None:
        for name in ("fixture_id", "market_key", "selection_key", "justification"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"{name}_REQUIRED")
        _positive("BANKROLL", self.bankroll_before)
        _probability("P_MATRIX", self.p_matrix)
        _positive("ENTRY_ODDS", self.entry_odds)
        _aware(self.frozen_at_utc, name="FROZEN_AT")
        _sha(self.clv_state_sha256, name="CLV_STATE")
        if isinstance(self.clv_closing_observations, bool) or self.clv_closing_observations < 0:
            raise ValueError("CLV_OBSERVATIONS_INVALID")
        if not 0 < float(self.requested_fractional_kelly) <= 0.5:
            raise ValueError("FRACTIONAL_KELLY_MUST_BE_IN_0_TO_HALF")
        if self.mode != "PAPER_ONLY" or self.real_money != "BLOCKED":
            raise ValueError("SIZING_MUST_REMAIN_PAPER_ONLY")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_clv_gated_paper_stake(
    *,
    fixture_id: str,
    market_key: str,
    selection_key: str,
    bankroll_before: float,
    p_matrix: float,
    entry_odds: float,
    frozen_at_utc: str,
    clv_state_sha256: str,
    clv_closing_observations: int,
    clv_metrics_opened: bool,
    clv_positive_confirmed: bool,
    fractional_kelly: float = 0.25,
    max_stake_fraction_bankroll: float = 0.005,
) -> PaperSizingDecision:
    bankroll = _positive("BANKROLL", bankroll_before)
    p = _probability("P_MATRIX", p_matrix)
    odds = _positive("ENTRY_ODDS", entry_odds)
    if not 0 < float(fractional_kelly) <= 0.5:
        raise ValueError("FULL_OR_EXCESSIVE_KELLY_FORBIDDEN")
    if not 0 < float(max_stake_fraction_bankroll) <= 0.01:
        raise ValueError("PAPER_STAKE_CAP_OUT_OF_POLICY")

    full = full_kelly_fraction(p, odds)
    status = "ELIGIBLE_PAPER_SIZING"
    justification = "CLV_GATE_PASS_AND_POSITIVE_MODEL_EDGE"
    applied = min(full * float(fractional_kelly), float(max_stake_fraction_bankroll))
    stake = bankroll * applied

    if not clv_metrics_opened:
        status = "BLOCKED_CLV_METRICS_SEALED"
        justification = "SIZING_NOT_ACTIVATED_BEFORE_CLV_MINIMUM_SAMPLE"
        applied = 0.0
        stake = 0.0
    elif not clv_positive_confirmed:
        status = "BLOCKED_CLV_NOT_POSITIVE_CONFIRMED"
        justification = "SIZING_REQUIRES_POSITIVE_CLV_CONFIRMATION"
        applied = 0.0
        stake = 0.0
    elif full <= 0:
        status = "BLOCKED_NON_POSITIVE_MODEL_EDGE"
        justification = "KELLY_EDGE_NOT_POSITIVE"
        applied = 0.0
        stake = 0.0

    return PaperSizingDecision(
        fixture_id=str(fixture_id),
        market_key=str(market_key),
        selection_key=str(selection_key),
        bankroll_before=bankroll,
        p_matrix=p,
        entry_odds=odds,
        frozen_at_utc=_aware(frozen_at_utc, name="FROZEN_AT").isoformat(),
        clv_state_sha256=_sha(clv_state_sha256, name="CLV_STATE"),
        clv_closing_observations=int(clv_closing_observations),
        requested_fractional_kelly=float(fractional_kelly),
        full_kelly_fraction=full,
        applied_bankroll_fraction=applied,
        stake_calculated=round(stake, 2),
        status=status,
        justification=justification,
    )


class PaperStakeLedger:
    """Append-only hash chain for future CLV-gated paper sizing decisions."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @staticmethod
    def _entry_hash(sequence: int, previous: str, decision: Mapping[str, Any]) -> str:
        return sha256(
            _canonical({
                "sequence": sequence,
                "previous_entry_sha256": previous,
                "decision": dict(decision),
            }).encode("utf-8")
        ).hexdigest()

    def load(self, *, verify: bool = True) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        previous = GENESIS_HASH
        with self.path.open("r", encoding="utf-8") as handle:
            for expected, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if verify:
                    if int(row.get("sequence", -1)) != expected:
                        raise ValueError("STAKE_LEDGER_SEQUENCE_BROKEN")
                    if row.get("previous_entry_sha256") != previous:
                        raise ValueError("STAKE_LEDGER_HASH_CHAIN_BROKEN")
                    expected_hash = self._entry_hash(
                        expected,
                        previous,
                        row.get("decision") or {},
                    )
                    if row.get("entry_sha256") != expected_hash:
                        raise ValueError("STAKE_LEDGER_ENTRY_HASH_MISMATCH")
                    decision = PaperSizingDecision(**dict(row.get("decision") or {}))
                    if decision.mode != "PAPER_ONLY" or decision.real_money != "BLOCKED":
                        raise ValueError("STAKE_LEDGER_REAL_MONEY_FORBIDDEN")
                rows.append(row)
                previous = str(row.get("entry_sha256") or "")
        return rows

    def append(self, decision: PaperSizingDecision) -> dict[str, Any]:
        if decision.status != "ELIGIBLE_PAPER_SIZING":
            raise ValueError("BLOCKED_SIZING_DECISION_CANNOT_BE_APPENDED_AS_STAKE")
        rows = self.load(verify=True)
        natural = (
            decision.fixture_id,
            decision.market_key,
            decision.selection_key,
            decision.frozen_at_utc,
        )
        for row in rows:
            prior = row["decision"]
            prior_key = (
                prior["fixture_id"],
                prior["market_key"],
                prior["selection_key"],
                prior["frozen_at_utc"],
            )
            if prior_key == natural:
                raise ValueError("DUPLICATE_STAKE_FREEZE")

        sequence = len(rows) + 1
        previous = rows[-1]["entry_sha256"] if rows else GENESIS_HASH
        payload = decision.as_dict()
        entry = {
            "sequence": sequence,
            "previous_entry_sha256": previous,
            "decision": payload,
            "entry_sha256": self._entry_hash(sequence, previous, payload),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(entry) + "\n")
            handle.flush()
        self.load(verify=True)
        return entry
