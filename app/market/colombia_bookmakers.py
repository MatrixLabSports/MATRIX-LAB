from __future__ import annotations

from dataclasses import dataclass

EXECUTION_BOOKMAKERS: dict[str, tuple[str, ...]] = {
    "betano": ("betano",),
    "betplay": ("betplay",),
    "betsson": ("betsson",),
    "bwin": ("bwin",),
    "codere": ("codere",),
    "luckia": ("luckia",),
    "mryoker": ("mryoker",),
    "rivalo": ("rivalo",),
    "rushbet": ("rushbet",),
    "sportium": ("sportiumco",),
    "stake": ("stake", "stakeco"),
    "wplay": ("wplay",),
    "yajuego": ("yajuego",),
    "zamba": ("zamba",),
}

REFERENCE_ONLY_BOOKMAKERS = frozenset({"pinnacle"})
QUARANTINED_BOOKMAKERS = frozenset({"unibet", "bingo_casino"})

@dataclass(frozen=True)
class BookmakerClassification:
    matrix_key: str | None
    provider_key: str
    role: str
    execution_eligible: bool

def classify_bookmaker(provider_key: str) -> BookmakerClassification:
    key = str(provider_key or "").strip().casefold()
    if not key:
        raise ValueError("BOOKMAKER_KEY_REQUIRED")
    for matrix_key, aliases in EXECUTION_BOOKMAKERS.items():
        if key in aliases:
            return BookmakerClassification(matrix_key, key, "EXECUTION_CANDIDATE", True)
    if key in REFERENCE_ONLY_BOOKMAKERS:
        return BookmakerClassification(None, key, "REFERENCE_ONLY", False)
    if key in QUARANTINED_BOOKMAKERS:
        return BookmakerClassification(None, key, "QUARANTINED", False)
    return BookmakerClassification(None, key, "UNKNOWN", False)
