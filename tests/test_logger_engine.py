from app.logger.logger_engine import MatrixLogger

def test_logger_creation(tmp_path):
    """
    Verifica que el Logger pueda inicializarse correctamente.
    """

    temp_log = tmp_path / "matrix.log"
    logger = MatrixLogger(log_file=temp_log)

    assert logger is not None
    logger.info("Prueba de auditoría")

    contenido = temp_log.read_text(encoding="utf-8")

    assert "Prueba de auditoría" in contenido

def test_logger_info():
    """
    Verifica que el método info() funcione correctamente.
    """

    logger = MatrixLogger()

    logger.info("Prueba de información")

    assert True

def test_log_file_exists(tmp_path):
    """
    Verifica que el archivo temporal de registro exista.
    """

    temp_log = tmp_path / "matrix.log"
    logger = MatrixLogger(log_file=temp_log)

    logger.info("Creando archivo de prueba")

    assert temp_log.exists()
    
def test_log_contains_message(tmp_path):
    """
    Verifica que el archivo temporal contenga el mensaje registrado.
    """

    temp_log = tmp_path / "matrix.log"
    logger = MatrixLogger(log_file=temp_log)

    message = "Mensaje de prueba MATRIX"

    logger.info(message)
    contenido = temp_log.read_text(encoding="utf-8")
    assert message in contenido