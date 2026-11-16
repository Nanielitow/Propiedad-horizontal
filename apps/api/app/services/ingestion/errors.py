class PermanentIngestionError(Exception):
    """Error que NO se arregla reintentando (PDF corrupto, cifrado, sin texto,
    hash que no coincide, configuración inválida). La tarea falla sin reintentos."""
