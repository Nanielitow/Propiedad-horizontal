"""Reglas puras de asambleas: quórum (arts. 41 y 45) y mayorías (arts. 45 y 46 de la Ley 675)."""

from datetime import date
from decimal import Decimal

from app.models.enums import ConvocatoriaAsamblea, MayoriaPunto
from app.services.asambleas import dominio as d

D = Decimal
P1, P2 = ConvocatoriaAsamblea.PRIMERA, ConvocatoriaAsamblea.SEGUNDA


def test_quorum_primera_convocatoria() -> None:
    assert not d.Quorum(D("50"), D("100"), 10, 50, P1).hay_quorum  # exactamente la mitad no basta
    q = d.Quorum(D("50.0001"), D("100"), 10, 50, P1)
    assert q.hay_quorum and q.falta == 0 and q.porcentaje == D("50.00")
    falta = d.Quorum(D("42.5"), D("100"), 10, 50, P1)
    assert falta.falta == D("7.5001") and "Sin quórum" in falta.mensaje


def test_quorum_segunda_convocatoria() -> None:
    assert d.Quorum(D("8"), D("100"), 2, 50, P2).hay_quorum  # número plural, cualquier coeficiente
    assert not d.Quorum(D("8"), D("100"), 1, 50, P2).hay_quorum


def test_mayoria_simple_sobre_los_presentes() -> None:
    # Presentes 60 %: aprobar exige más de 30 % a favor
    r = d.resultado(
        MayoriaPunto.SIMPLE,
        ["Sí", "No", "Abstención"],
        [("Sí", D("30.01")), ("No", D("20")), ("Abstención", D("9.99"))],
        presente=D("60"),
        total=D("100"),
    )
    assert r.aprobado and r.umbral == D("30") and r.unidades_por_opcion == {"Sí": 1, "No": 1, "Abstención": 1}
    empate = d.resultado(
        MayoriaPunto.SIMPLE, ["Sí", "No"], [("Sí", D("30")), ("No", D("30"))], presente=D("60"), total=D("100")
    )
    assert not empate.aprobado  # la mitad no es la mitad más uno


def test_mayoria_calificada_sobre_el_total() -> None:
    # 65 de 70 presentes votan sí (93 % de los presentes) pero no es el 70 % del conjunto
    r = d.resultado(
        MayoriaPunto.CALIFICADA_70, ["Sí", "No"], [("Sí", D("65")), ("No", D("5"))], presente=D("70"), total=D("100")
    )
    assert not r.aprobado and r.umbral == D("70") and "art. 46" in r.explicacion
    assert d.resultado(
        MayoriaPunto.CALIFICADA_70, ["Sí", "No"], [("Sí", D("70"))], presente=D("75"), total=D("100")
    ).aprobado


def test_eleccion() -> None:
    r = d.resultado(
        MayoriaPunto.ELECCION,
        ["Plancha 1", "Plancha 2"],
        [("Plancha 1", D("30")), ("Plancha 2", D("25"))],
        presente=D("55"),
        total=D("100"),
    )
    assert r.ganador == "Plancha 1" and r.aprobado is None
    empate = d.resultado(
        MayoriaPunto.ELECCION, ["A", "B"], [("A", D("20")), ("B", D("20"))], presente=D("40"), total=D("100")
    )
    assert empate.ganador is None and "Empate" in empate.explicacion


def test_convocatoria_y_opciones() -> None:
    assert d.aviso_convocatoria(date(2027, 3, 13), date(2027, 2, 26)) is None  # 15 días
    assert "14 día(s)" in (d.aviso_convocatoria(date(2027, 3, 13), date(2027, 2, 27)) or "")
    assert d.normalizar_opciones([], MayoriaPunto.SIMPLE) == ["Sí", "No", "Abstención"]
    assert d.normalizar_opciones([" Ana  Ruiz ", "ana ruiz", "Luis"], MayoriaPunto.ELECCION) == ["Ana Ruiz", "Luis"]
