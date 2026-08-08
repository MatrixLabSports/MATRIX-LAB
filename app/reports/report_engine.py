from dataclasses import dataclass
from datetime import datetime
import json

from config.settings import REPORTS_FILE
from app.logger.logger_engine import MatrixLogger


@dataclass
class MatrixReport:
    created_at: str
    player1: str
    player2: str
    tournament: str
    filter_score: int
    matrix_score: float
    risk_score: float
    risk_level: str
    confidence: str
    decision: str


class MatrixReportEngine:
    """
    Motor encargado de almacenar los análisis de MATRIX.
    """
    def __init__(
        self,
        output_file: str = REPORTS_FILE,
        logger: MatrixLogger | None = None,
    ):
        self.output_file = output_file
        self.logger = logger or MatrixLogger()
    def save_report(self, report: MatrixReport):

        try:
            with open(self.output_file, "r", encoding="utf-8") as file:
                reports = json.load(file)

        except FileNotFoundError:
            reports = []

        except json.JSONDecodeError as error:
            self.logger.error(
                f"No fue posible leer el archivo de reportes: "
                f"JSON inválido. {error}"
            )
            raise ValueError(
                "El archivo de reportes contiene un JSON inválido."
            ) from error

        reports.append(report.__dict__)

        with open(self.output_file, "w", encoding="utf-8") as file:

            json.dump(
                reports,
                file,
                indent=4,
                ensure_ascii=False,
            )

        self.logger.info("Reporte guardado correctamente.")