import json
import pytest

from datetime import datetime

from app.reports.report_engine import (
        MatrixReport,
        MatrixReportEngine,
    )

def test_save_report(tmp_path):

        temp_file = tmp_path / "temp_reports.json"

        engine = MatrixReportEngine(
            output_file=str(temp_file),
    )

        report = MatrixReport(
                        created_at=datetime.now().isoformat(timespec="seconds"),
                        player1="Jugador Prueba 1",
                                player2="Jugador Prueba 2",
            tournament="Torneo de Prueba",
            filter_score=7,
            matrix_score=85.0,
            risk_score=20.0,
            risk_level="BAJO",
            confidence="ALTA",
            decision="PRUEBA",
        )
        engine.save_report(report)
        with open(temp_file, "r", encoding="utf-8") as file:
            reports = json.load(file)
        assert len(reports) == 1
        assert reports[0]["player1"] == "Jugador Prueba 1"
        assert reports[0]["player2"] == "Jugador Prueba 2"
        assert reports[0]["tournament"] == "Torneo de Prueba"
        assert reports[0]["filter_score"] == 7
        assert reports[0]["matrix_score"] == 85.0
        assert reports[0]["risk_score"] == 20.0
        assert reports[0]["risk_level"] == "BAJO"
        assert reports[0]["confidence"] == "ALTA"
        assert reports[0]["decision"] == "PRUEBA"
        assert temp_file.exists()

def test_invalid_json_is_not_overwritten(tmp_path):
    """
    Verifica que un JSON inválido no sea sobrescrito.
    """

    temp_file = tmp_path / "temp_reports.json"
    contenido_corrupto = "{json_invalido"

    temp_file.write_text(
        contenido_corrupto,
        encoding="utf-8",
    )

    engine = MatrixReportEngine(
        output_file=str(temp_file),
    )

    report = MatrixReport(
        created_at=datetime.now().isoformat(timespec="seconds"),
        player1="Jugador Prueba 1",
        player2="Jugador Prueba 2",
        tournament="Torneo de Prueba",
        filter_score=7,
        matrix_score=85.0,
        risk_score=20.0,
        risk_level="BAJO",
        confidence="ALTA",
        decision="PRUEBA",
    )

    with pytest.raises(ValueError):
        engine.save_report(report)

    contenido_final = temp_file.read_text(encoding="utf-8")

    assert contenido_final == contenido_corrupto


def test_matrix_report_exposes_score_band_label():
    report = MatrixReport(
        created_at="2026-08-14T12:00:00",
        player1="Player A",
        player2="Player B",
        tournament="Test Tournament",
        filter_score=7,
        matrix_score=80.0,
        risk_score=20.0,
        risk_level="BAJO",
        confidence="ALTA",
        decision="CANDIDATO PARA REVISIÓN",
    )

    assert report.score_band_label == "ALTA"
