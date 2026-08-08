"""
MATRIX-LAB-SPORTS

Motor principal de análisis para tenis.
"""


class MatrixEngine:

    def __init__(self):
        self.version = "0.1"
        self.name = "MATRIX TENIS"

    def start(self):
        print("==========================")
        print("MATRIX TENIS INICIADO")
        print("==========================")
        print(f"Motor: {self.name}")
        print(f"Versión: {self.version}")
        print("Sistema listo para analizar partidos.")

    def registrar_partido(self, jugador1, jugador2, torneo):
        print("==========================")
        print("NUEVO PARTIDO")
        print("==========================")
        print(f"Jugador 1: {jugador1}")
        print(f"Jugador 2: {jugador2}")
        print(f"Torneo: {torneo}")
        print("==========================")


if __name__ == "__main__":
    engine = MatrixEngine()
    engine.start()
    engine.registrar_partido(
        "Michael Zheng",
        "Miomir Kecmanovic",
        "Montreal"
    )