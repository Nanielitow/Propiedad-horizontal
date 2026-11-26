"""Restablecer los conjuntos de demostración sin tocar las copropiedades reales.

Corre con el rol dueño y confirma su propia transacción (como en producción), así que NO usa el fixture `mundo`:
el ALTER TABLE ... DISABLE TRIGGER esperaría a que terminara la transacción de la prueba.
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.services import demo

pytestmark = pytest.mark.integration


@pytest.fixture
def owner():  # type: ignore[no-untyped-def]
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        pytest.skip("MIGRATIONS_DATABASE_URL no configurada")
    engine = create_engine(url)
    with engine.connect() as c:
        hay = c.execute(
            text("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'demo_snapshot'")
        ).scalar()
    if not hay:
        pytest.skip("No hay instantánea de la demo en la base local")
    yield engine
    engine.dispose()


def test_restablece_la_demo_y_respeta_las_reales(owner) -> None:  # type: ignore[no-untyped-def]
    real = uuid.uuid4()
    with owner.begin() as c:
        demo_id = c.execute(text("SELECT id FROM demo_snapshot.tenants ORDER BY name LIMIT 1")).scalar_one()
        esperadas = c.execute(
            text("SELECT count(*) FROM demo_snapshot.units WHERE tenant_id = :t"), {"t": demo_id}
        ).scalar_one()
        # Una copropiedad real con su unidad, y «basura» de un visitante en la demo
        c.execute(
            text("INSERT INTO tenants (id, name, slug) VALUES (:id, 'Conjunto Real de Prueba', :s)"),
            {"id": real, "s": f"real-{real}"},
        )
        c.execute(
            text("INSERT INTO units (tenant_id, tower, number, coefficient) VALUES (:t, '9', '901', 1)"), {"t": real}
        )
        c.execute(
            text("INSERT INTO units (tenant_id, tower, number, coefficient) VALUES (:t, 'V', '999', 1)"), {"t": demo_id}
        )
    try:
        demo.restablecer_conjuntos_demo()
        with owner.connect() as c:
            assert (
                c.execute(text("SELECT count(*) FROM units WHERE tenant_id = :t"), {"t": demo_id}).scalar_one()
                == esperadas
            )
            assert (
                c.execute(
                    text("SELECT count(*) FROM units WHERE tenant_id = :t AND number = '999'"), {"t": demo_id}
                ).scalar_one()
                == 0
            )
            assert c.execute(text("SELECT count(*) FROM units WHERE tenant_id = :t"), {"t": real}).scalar_one() == 1
            assert c.execute(
                text("SELECT bool_and(is_demo) FROM tenants WHERE id IN (SELECT id FROM demo_snapshot.tenants)")
            ).scalar_one()

        # Si un conjunto de la instantánea se marcó como real, no se toca nada
        with owner.begin() as c:
            c.execute(text("UPDATE tenants SET is_demo = false WHERE id = :t"), {"t": demo_id})
        with pytest.raises(RuntimeError, match="ya no están marcados como demostración"):
            demo.restablecer_conjuntos_demo()
    finally:
        with owner.begin() as c:
            c.execute(text("UPDATE tenants SET is_demo = true WHERE id = :t"), {"t": demo_id})
            with demo.sin_triggers(c):
                c.execute(text("DELETE FROM auditoria_unidades WHERE tenant_id = :t"), {"t": real})
                c.execute(text("DELETE FROM units WHERE tenant_id = :t"), {"t": real})
                c.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": real})
