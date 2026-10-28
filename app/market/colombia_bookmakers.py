from __future__ import annotations

from dataclasses import dataclass

EXECUTION_BOOKMAKERS: dict[str, tuple[str, ...]] = {
    "betano": ("betano",),
    "betplay": ("betplay",),
    "betsson": ("betsson",),
    "bwin": ("bwin",),
    "codere": ("codere",),
    "luckia": ("luckia",),
    "mryoker": ("mryoker", "mr yoker", "mr. yoker"),
    "rivalo": ("rivalo",),
    "rushbet": ("rushbet", "rush bet"),
    "sportium": ("sportiumco", "sportium"),
    "stake": ("stake", "stakeco"),
    "wplay": ("wplay", "w play"),
    "yajuego": ("yajuego", "ya juego"),
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
            return BookmakerClassification(
                matrix_key=matrix_key,
                provider_key=key,
                role="EXECUTION_CANDIDATE",
                execution_eligible=True,
            )
    if key in REFERENCE_ONLY_BOOKMAKERS:
        return BookmakerClassification(
            matrix_key=None,
            provider_key=key,
            role="REFERENCE_ONLY",
            execution_eligible=False,
        )
    if key in QUARANTINED_BOOKMAKERS:
        return BookmakerClassification(
            matrix_key=None,
            provider_key=key,
            role="QUARANTINED",
            execution_eligible=False,
        )
    return BookmakerClassification(
        matrix_key=None,
        provider_key=key,
        role="UNKNOWN",
        execution_eligible=False,
    )
