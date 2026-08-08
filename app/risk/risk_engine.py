from dataclasses import dataclass


@dataclass
class RiskResult:
    risk_score: float
    level: str
    allowed_to_continue: bool
    positive_factors: list[str]
    warnings: list[str]


class MatrixRiskEngine:
    """
    Primera versión del motor de riesgo.

    Un resultado bajo significa menor riesgo.
    Un resultado alto significa mayor riesgo.
    """

    def __init__(self) -> None:
        self.name = "MATRIX RISK ENGINE"
        self.version = "0.1"

    def evaluate_risk(
        self,
        data_risk: float,
        statistical_risk: float,
        sporting_risk: float,
        market_risk: float,
        operational_risk: float,
    ) -> RiskResult:
        risks = {
            "data_risk": data_risk,
            "statistical_risk": statistical_risk,
            "sporting_risk": sporting_risk,
            "market_risk": market_risk,
            "operational_risk": operational_risk,
        }

        self._validate_inputs(risks)

        weights = {
            "data_risk": 0.25,
            "statistical_risk": 0.20,
            "sporting_risk": 0.25,
            "market_risk": 0.20,
            "operational_risk": 0.10,
        }

        risk_score = sum(
            risks[name] * weights[name]
            for name in risks
        )

        level, allowed = self._classify_risk(risk_score)
        positive_factors, warnings = self._build_explanation(risks)

        return RiskResult(
            risk_score=round(risk_score, 2),
            level=level,
            allowed_to_continue=allowed,
            positive_factors=positive_factors,
            warnings=warnings,
        )

    def _validate_inputs(
        self,
        risks: dict[str, float],
    ) -> None:
        for name, value in risks.items():
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"El valor '{name}' debe ser numérico."
                )

            if not 0 <= value <= 100:
                raise ValueError(
                    f"El valor '{name}' debe estar entre 0 y 100."
                )

    def _classify_risk(
        self,
        risk_score: float,
    ) -> tuple[str, bool]:
        if risk_score <= 25:
            return "BAJO", True

        if risk_score <= 50:
            return "MEDIO", True

        if risk_score <= 75:
            return "ALTO", False

        return "CRÍTICO", False

    def _build_explanation(
        self,
        risks: dict[str, float],
    ) -> tuple[list[str], list[str]]:
        labels = {
            "data_risk": "Riesgo de datos",
            "statistical_risk": "Riesgo estadístico",
            "sporting_risk": "Riesgo deportivo",
            "market_risk": "Riesgo de mercado",
            "operational_risk": "Riesgo operacional",
        }

        positive_factors: list[str] = []
        warnings: list[str] = []

        for name, value in risks.items():
            label = labels[name]

            if value <= 25:
                positive_factors.append(
                    f"{label} controlado ({value}/100)."
                )
            elif value <= 50:
                warnings.append(
                    f"{label} moderado ({value}/100)."
                )
            else:
                warnings.append(
                    f"{label} elevado ({value}/100)."
                )

        return positive_factors, warnings


if __name__ == "__main__":
    engine = MatrixRiskEngine()

    result = engine.evaluate_risk(
        data_risk=10,
        statistical_risk=30,
        sporting_risk=25,
        market_risk=35,
        operational_risk=10,
    )

    print("=" * 50)
    print(f"{engine.name} - VERSION {engine.version}")
    print("=" * 50)
    print(f"Índice de riesgo: {result.risk_score}/100")
    print(f"Nivel: {result.level}")
    print(
        "Puede continuar:",
        "SÍ" if result.allowed_to_continue else "NO",
    )

    print("\nFactores positivos:")
    for factor in result.positive_factors:
        print(f"- {factor}")

    print("\nAdvertencias:")
    for warning in result.warnings:
        print(f"- {warning}")