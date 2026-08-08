"""
Motor de registro de eventos de MATRIX.

Este módulo centraliza todos los mensajes del sistema
para facilitar auditorías, depuración y monitoreo.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

class MatrixLogger:
    """
    Motor encargado del registro de eventos del sistema MATRIX.
    """

    def __init__(self, log_file: Path | None = None):
        """
        Inicializa el sistema de registro de eventos.
        """
        self.logs_folder = Path("logs")
        self.logs_folder.mkdir(exist_ok=True)

        if log_file is None:
            log_file = self.logs_folder / "matrix.log"

        self.log_file = log_file

        self.logger = logging.getLogger("matrix")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)

        file_handler = RotatingFileHandler(
        self.log_file,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
        )

        formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
        )

        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    

    def info(self, message: str) -> None:
        """
        Registra un evento informativo del sistema.
        """
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """
        Registra una advertencia del sistema.
        """
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """
        Registra un error del sistema.
        """
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """
        Registra un error crítico del sistema.
        """
        self.logger.critical(message)