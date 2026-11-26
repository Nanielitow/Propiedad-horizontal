"""Respaldos: retención, conexión sin exponer la contraseña y claves válidas para descargar."""

from datetime import date

from app.services import respaldos as r


def test_retencion_diarios_30_dias_y_mensuales_12_meses() -> None:
    hoy = date(2026, 11, 26)
    claves = [
        "respaldos/diarios/ph-2026-11-26-0300.dump",
        "respaldos/diarios/ph-2026-10-27-0300.dump",  # 30 días: se conserva
        "respaldos/diarios/ph-2026-10-26-0300.dump",  # 31 días: sale
        "respaldos/diarios/ph-2026-01-01-0300.dump",
        "respaldos/mensuales/ph-2026-11.dump",
        "respaldos/mensuales/ph-2025-12.dump",  # dentro de los 12 meses
        "respaldos/mensuales/ph-2025-11.dump",  # mismo mes del año pasado: sale
        "respaldos/mensuales/ph-2024-03.dump",
        "respaldos/otra-cosa.txt",  # sin fecha: nunca se toca
    ]
    assert sorted(r.claves_vencidas(claves, hoy)) == sorted(
        [
            "respaldos/diarios/ph-2026-10-26-0300.dump",
            "respaldos/diarios/ph-2026-01-01-0300.dump",
            "respaldos/mensuales/ph-2025-11.dump",
            "respaldos/mensuales/ph-2024-03.dump",
        ]
    )


def test_retencion_en_enero_cruza_el_anio() -> None:
    claves = ["respaldos/mensuales/ph-2026-01.dump", "respaldos/mensuales/ph-2026-02.dump"]
    assert r.claves_vencidas(claves, date(2027, 1, 15)) == ["respaldos/mensuales/ph-2026-01.dump"]


def test_conexion_por_variables_de_entorno() -> None:
    env = r._entorno_libpq("postgresql+psycopg://dueno:cl%40ve-secreta@db.ejemplo.co:5433/ph?sslmode=require")
    assert env == {
        "PGHOST": "db.ejemplo.co",
        "PGPORT": "5433",
        "PGDATABASE": "ph",
        "PGUSER": "dueno",
        "PGPASSWORD": "cl@ve-secreta",
        "PGCONNECT_TIMEOUT": "20",
        "PGSSLMODE": "require",
    }
    # Un mensaje de error de pg_dump nunca deja ver la contraseña ni el usuario
    assert r._limpiar('FATAL: password authentication failed for user "dueno" (cl@ve-secreta)', env) == (
        'FATAL: password authentication failed for user "***" (***)'
    )


def test_claves_descargables() -> None:
    assert r.es_clave_valida("respaldos/diarios/ph-2026-11-26-0300.dump")
    assert r.es_clave_valida("respaldos/mensuales/ph-2026-11.dump")
    for mala in (
        "tenants/abc/documents/x.pdf",
        "respaldos/diarios/../../tenants/x.dump",
        "respaldos/diarios/ph.txt",
        "respaldos/diarios/ph 1.dump",
    ):
        assert not r.es_clave_valida(mala), mala
