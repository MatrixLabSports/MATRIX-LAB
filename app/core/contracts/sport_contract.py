from dataclasses import dataclass


@dataclass(frozen=True)
class SportContract:
    """
    Contrato base que identifica un deporte dentro de MATRIX.
    """

    code: str
    name: str
    version: str = "1.0"

    def __post_init__(self):
        if not self.code.strip():
            raise ValueError("El código del deporte no puede estar vacío.")

        if not self.name.strip():
            raise ValueError("El nombre del deporte no puede estar vacío.")