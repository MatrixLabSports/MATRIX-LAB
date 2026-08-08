from app.core.contracts.sport_contract import SportContract


SPORT_REGISTRY = {
    "TENNIS": SportContract(
        code="TENNIS",
        name="Tennis",
    ),
    "FOOTBALL": SportContract(
        code="FOOTBALL",
        name="Football",
    ),
}


def get_sport(code: str) -> SportContract:
    """
    Devuelve el contrato correspondiente a un deporte registrado.
    """

    normalized_code = code.strip().upper()

    if normalized_code not in SPORT_REGISTRY:
        raise ValueError(
            f"Deporte no registrado en MATRIX: {code}"
        )

    return SPORT_REGISTRY[normalized_code]