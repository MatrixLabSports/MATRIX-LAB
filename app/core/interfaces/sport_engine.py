from abc import ABC, abstractmethod
from typing import Any


class SportEngine(ABC):
    """
    Contrato base obligatorio para cualquier motor deportivo
    conectado a MATRIX CORE.
    """

    @property
    @abstractmethod
    def sport_code(self) -> str:
        """Identificador único del deporte."""
        raise NotImplementedError

    @abstractmethod
    def validate_match(self, match: Any) -> bool:
        """Valida si un partido cumple las reglas del deporte."""
        raise NotImplementedError

    @abstractmethod
    def process_match(self, match: Any) -> Any:
        """Procesa un partido válido dentro del motor deportivo."""
        raise NotImplementedError