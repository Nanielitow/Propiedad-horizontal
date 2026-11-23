"""Reglas del módulo de recaudos impuestas POR LA BASE DE DATOS (migración 0003).

Se conectan como app_user (el rol de la API) dentro de una transacción que se
revierte al final. Cada intento que debe fallar va en un SAVEPOINT
(begin_nested) para poder seguir usando la conexión.
"""

import os
import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.integration


@pytest.fixture
def conn() -> Iterator[Connection]:
    url = os.environ.get("SYNC_DATABASE_URL")
    if not url:
        pytest.skip("SYNC_DATABASE_URL no configurada")
    engine = create_engine(url)
    with engine.connect() as connection:
        tx = connection.begin()
        try:
            yield connection
        finally:
            tx.rollback()
    engine.dispose()


def como(conn: Connection, tenant: uuid.UUID, rol: str, usuario: uuid.UUID | None = None, motivo: str = "") -> None:
    for clave, valor in (("tenant_id", tenant), ("role", rol), ("user_id", usuario or ""), ("motivo", motivo)):
        conn.execute(text("SELECT set_config(:k, :v, true)"), {"k": f"app.{clave}", "v": str(valor)})


def nuevo_tenant(conn: Connection) -> uuid.UUID:
    tenant = uuid.uuid4()
    conn.execute(
        text("INSERT INTO tenants (id, name, slug) VALUES (:id, 'Conjunto de prueba', :s)"),
        {"id": tenant, "s": f"test-{tenant}"},
    )
    como(conn, tenant, "SYSTEM")
    conn.execute(text("SELECT seed_conceptos_recaudo(:t)"), {"t": tenant})
    return tenant


def nuevo_usuario(conn: Connection) -> uuid.UUID:
    user = uuid.uuid4()
    conn.execute(
        text("INSERT INTO users (id, email, full_name, password_hash) VALUES (:id, :e, 'Prueba', 'x')"),
        {"id": user, "e": f"{user}@test.local"},
    )
    return user


def concepto(conn: Connection, codigo: str) -> uuid.UUID:
    return conn.scalar(text("SELECT id FROM conceptos_recaudo WHERE codigo = :c"), {"c": codigo})


def recaudo(
    conn: Connection,
    tenant: uuid.UUID,
    receptor: uuid.UUID,
    *,
    medio: str = "EFECTIVO",
    valor: int = 10000,
    estado: str = "VERIFICADO",  # se envía a propósito: el trigger debe ignorarlo
    item: int | None = None,
) -> tuple[uuid.UUID, int, str]:
    concepto_id = concepto(conn, "OTROS")
    row = conn.execute(
        text(
            "INSERT INTO recaudos (tenant_id, concepto_id, valor_recibido, nombre_pagador, medio_pago, estado,"
            " numero_comprobante, usuario_receptor_id)"
            " VALUES (:t, :c, :v, 'Visitante', CAST(:m AS medio_pago), CAST(:e AS estado_recaudo), 'TRX-1', :u)"
            " RETURNING id, consecutivo, estado::text"
        ),
        {"t": tenant, "c": concepto_id, "v": valor, "m": medio, "e": estado, "u": receptor},
    ).one()
    conn.execute(
        text("INSERT INTO recaudo_items (tenant_id, recaudo_id, concepto_id, valor) VALUES (:t, :r, :c, :v)"),
        {"t": tenant, "r": row[0], "c": concepto_id, "v": item if item is not None else valor},
    )
    return row[0], row[1], row[2]


def falla(conn: Connection, sql: str, params: dict[str, object], match: str) -> None:
    with pytest.raises(DBAPIError, match=match), conn.begin_nested():
        conn.execute(text(sql), params)


@pytest.fixture
def mundo(conn: Connection) -> dict[str, uuid.UUID]:
    t = nuevo_tenant(conn)
    return {"t": t, "admin": nuevo_usuario(conn), "aux1": nuevo_usuario(conn), "aux2": nuevo_usuario(conn)}


# --- Consecutivos y estado inicial ------------------------------------------------


def test_consecutivo_sin_huecos_e_independiente_por_copropiedad(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    assert [recaudo(conn, mundo["t"], mundo["admin"])[1] for _ in range(3)] == [1, 2, 3]

    otro = nuevo_tenant(conn)
    como(conn, otro, "ADMIN", mundo["admin"])
    assert recaudo(conn, otro, mundo["admin"])[1] == 1


def test_estado_inicial_lo_fija_la_base_segun_el_medio(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    assert recaudo(conn, mundo["t"], mundo["admin"], medio="EFECTIVO")[2] == "RECAUDADO_EN_CAJA"
    assert recaudo(conn, mundo["t"], mundo["admin"], medio="TRANSFERENCIA")[2] == "PENDIENTE_VERIFICACION"


# --- Inmutabilidad -------------------------------------------------------------------


def test_nadie_puede_borrar_un_recaudo(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    falla(conn, "DELETE FROM recaudos WHERE id = :id", {"id": rid}, "permission denied")
    falla(conn, "DELETE FROM recaudo_items WHERE recaudo_id = :id", {"id": rid}, "permission denied")


def test_el_valor_no_se_puede_modificar(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    falla(conn, "UPDATE recaudos SET valor_recibido = 1 WHERE id = :id", {"id": rid}, "no se pueden modificar")
    falla(conn, "UPDATE recaudo_items SET valor = 1 WHERE recaudo_id = :id", {"id": rid}, "inmutables")


def test_transicion_fuera_del_diagrama_es_rechazada(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    falla(
        conn,
        "UPDATE recaudos SET estado = 'VERIFICADO', verificado_por_id = :u, verificado_at = now() WHERE id = :id",
        {"id": rid, "u": mundo["admin"]},
        "Transición de estado no permitida",
    )


def test_anulacion_exige_motivo_y_es_definitiva(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    falla(
        conn,
        "UPDATE recaudos SET estado = 'ANULADO', anulado_por_id = :u, anulado_at = now() WHERE id = :id",
        {"id": rid, "u": mundo["admin"]},
        "check constraint",
    )
    conn.execute(
        text(
            "UPDATE recaudos SET estado = 'ANULADO', anulado_por_id = :u, anulado_at = now(),"
            " motivo_anulacion = 'Registro duplicado por error' WHERE id = :id"
        ),
        {"id": rid, "u": mundo["admin"]},
    )
    falla(conn, "UPDATE recaudos SET observaciones = 'x' WHERE id = :id", {"id": rid}, "anulado no admite")


def test_desglose_que_no_cuadra_falla_al_confirmar(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    with pytest.raises(DBAPIError, match="desglose"), conn.begin_nested():
        recaudo(conn, mundo["t"], mundo["admin"], valor=10000, item=9000)
        conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    recaudo(conn, mundo["t"], mundo["admin"], valor=10000)
    conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))  # el que sí cuadra pasa


# --- Permisos por rol (RLS + trigger) ------------------------------------------


def test_auxiliar_solo_ve_lo_que_recibio(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    t = mundo["t"]
    como(conn, t, "AUXILIAR", mundo["aux1"])
    propio, _, _ = recaudo(conn, t, mundo["aux1"])
    como(conn, t, "AUXILIAR", mundo["aux2"])
    recaudo(conn, t, mundo["aux2"])

    como(conn, t, "AUXILIAR", mundo["aux1"])
    assert set(conn.scalars(text("SELECT id FROM recaudos"))) == {propio}
    como(conn, t, "CONTABILIDAD", mundo["admin"])
    assert conn.scalar(text("SELECT count(*) FROM recaudos")) == 2
    for rol in ("CONSEJO", "RESIDENTE"):
        como(conn, t, rol, mundo["admin"])
        assert conn.scalar(text("SELECT count(*) FROM recaudos")) == 0


def test_auxiliar_no_registra_a_nombre_de_otro(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "AUXILIAR", mundo["aux1"])
    with pytest.raises(DBAPIError, match="row-level security"), conn.begin_nested():
        recaudo(conn, mundo["t"], mundo["aux2"])


def test_contabilidad_y_consejo_no_registran(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    for rol in ("CONTABILIDAD", "CONSEJO"):
        como(conn, mundo["t"], rol, mundo["admin"])
        with pytest.raises(DBAPIError, match="row-level security"), conn.begin_nested():
            recaudo(conn, mundo["t"], mundo["admin"])


def test_auxiliar_no_anula_ni_cambia_estados(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "AUXILIAR", mundo["aux1"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["aux1"])
    falla(
        conn,
        "UPDATE recaudos SET estado = 'ANULADO', anulado_por_id = :u, anulado_at = now(),"
        " motivo_anulacion = 'Intento de anulación del auxiliar' WHERE id = :id",
        {"id": rid, "u": mundo["aux1"]},
        "Solo la administración puede anular",
    )
    falla(
        conn,
        "UPDATE recaudos SET estado = 'ENTREGADO_ADMINISTRACION' WHERE id = :id",
        {"id": rid},
        "no puede cambiar el estado",
    )


def test_contabilidad_verifica_pero_no_edita(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"], medio="TRANSFERENCIA")
    como(conn, mundo["t"], "CONTABILIDAD", mundo["aux2"])
    falla(conn, "UPDATE recaudos SET observaciones = 'x' WHERE id = :id", {"id": rid}, "no puede editar")
    conn.execute(
        text("UPDATE recaudos SET estado = 'VERIFICADO', verificado_por_id = :u, verificado_at = now() WHERE id = :id"),
        {"id": rid, "u": mundo["aux2"]},
    )


def test_concepto_de_otra_copropiedad_es_imposible(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    ajeno = concepto(conn, "OTROS")
    otro = nuevo_tenant(conn)
    como(conn, otro, "ADMIN", mundo["admin"])
    with pytest.raises(IntegrityError, match="foreign key"), conn.begin_nested():
        conn.execute(
            text(
                "INSERT INTO recaudos (tenant_id, concepto_id, valor_recibido, nombre_pagador, medio_pago,"
                " estado, usuario_receptor_id) VALUES (:t, :c, 1000, 'Visitante', 'EFECTIVO', 'RECAUDADO_EN_CAJA', :u)"
            ),
            {"t": otro, "c": ajeno, "u": mundo["admin"]},
        )


# --- Auditoría ------------------------------------------------------------------------


def test_auditoria_automatica_solo_con_campos_cambiados_y_motivo(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    como(conn, mundo["t"], "ADMIN", mundo["admin"], motivo="Se corrige el nombre del pagador")
    conn.execute(text("UPDATE recaudos SET nombre_pagador = 'Ana Ruiz' WHERE id = :id"), {"id": rid})

    filas = conn.execute(
        text(
            "SELECT accion::text, valores_anteriores, valores_nuevos, motivo, usuario_id"
            " FROM auditoria_recaudos WHERE recaudo_id = :id ORDER BY id"
        ),
        {"id": rid},
    ).all()
    assert [f[0] for f in filas] == ["CREACION", "EDICION"]
    _, antes, despues, motivo, usuario = filas[1]
    assert antes == {"nombre_pagador": "Visitante"}
    assert despues == {"nombre_pagador": "Ana Ruiz"}
    assert motivo == "Se corrige el nombre del pagador"
    assert usuario == mundo["admin"]


def test_auditoria_no_se_escribe_ni_se_altera_a_mano(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    params = {"t": mundo["t"], "id": rid}
    falla(
        conn,
        "INSERT INTO auditoria_recaudos (tenant_id, entidad, entidad_id, accion) VALUES (:t, 'recaudo', :id, 'EDICION')",
        params,
        "permission denied",
    )
    falla(conn, "UPDATE auditoria_recaudos SET motivo = 'x' WHERE recaudo_id = :id", params, "permission denied")
    falla(conn, "DELETE FROM auditoria_recaudos WHERE recaudo_id = :id", params, "permission denied")
    falla(conn, "UPDATE secuencias SET ultimo = 0", {}, "permission denied")


# --- Caja, parqueadero y consignaciones --------------------------------------------


def test_cierre_con_diferencia_exige_justificacion(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "AUXILIAR", mundo["aux1"])
    sql = (
        "INSERT INTO cierres_caja (tenant_id, usuario_id, inicio_turno, saldo_esperado_sistema, valor_fisico_contado,"
        " observacion_justificacion) VALUES (:t, :u, now() - interval '8 hours', 100000, 90000, :j)"
        " RETURNING id, diferencia, tipo_diferencia, consecutivo"
    )
    base = {"t": mundo["t"], "u": mundo["aux1"]}
    falla(conn, sql, {**base, "j": None}, "check constraint")
    cid, diferencia, tipo, consecutivo = conn.execute(
        text(sql), {**base, "j": "Se dio mal el cambio a un visitante"}
    ).one()
    assert (diferencia, tipo, consecutivo) == (Decimal("-10000.00"), "FALTANTE", 1)
    falla(conn, "UPDATE cierres_caja SET valor_fisico_contado = 100000 WHERE id = :id", {"id": cid}, "inmutables")


def test_parqueadero_calcula_minutos_y_valida_placa(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    como(conn, mundo["t"], "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, mundo["t"], mundo["admin"])
    sql = (
        "INSERT INTO recaudo_parqueadero (recaudo_id, tenant_id, placa_vehiculo, hora_ingreso, hora_salida,"
        " tarifa_sugerida) VALUES (:r, :t, :p, now() - interval '90 minutes', now(), 4000) RETURNING minutos_totales"
    )
    falla(conn, sql, {"r": rid, "t": mundo["t"], "p": "abc-123"}, "check constraint")
    assert conn.scalar(text(sql), {"r": rid, "t": mundo["t"], "p": "ABC123"}) == 90


def test_no_se_consigna_mas_que_el_valor_del_recaudo(conn: Connection, mundo: dict[str, uuid.UUID]) -> None:
    t = mundo["t"]
    como(conn, t, "ADMIN", mundo["admin"])
    rid, _, _ = recaudo(conn, t, mundo["admin"], valor=50000)
    consignacion = conn.scalar(
        text(
            "INSERT INTO consignaciones (tenant_id, fecha_consignacion, banco_destino, referencia_bancaria,"
            " valor_consignado, usuario_consigna_id) VALUES (:t, current_date, 'Bancolombia', 'REF-1', 30000, :u)"
            " RETURNING id"
        ),
        {"t": t, "u": mundo["admin"]},
    )
    sql = (
        "INSERT INTO consignacion_recaudos (consignacion_id, recaudo_id, tenant_id, valor_aplicado)"
        " VALUES (:c, :r, :t, :v)"
    )
    falla(conn, sql, {"c": consignacion, "r": rid, "t": t, "v": 60000}, "supera su valor")
    conn.execute(text(sql), {"c": consignacion, "r": rid, "t": t, "v": 30000})  # consignación parcial: válida
