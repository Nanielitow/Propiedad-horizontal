"""Filtro de destinatarios del correo: nunca escribir a dominios ficticios ni, en la demo, a terceros."""

from types import SimpleNamespace

import pytest

from app.services.notifications import email

TODOS = ["admin@lospinos.demo", "ana@gmail.com", "x@algo.local", "Dueño@Empresa.co", "malo", "y@sin-punto"]


def _settings(monkeypatch: pytest.MonkeyPatch, **kw: object) -> None:
    base = {"environment": "production", "demo_mode": False, "smtp_demo_recipients": ""}
    monkeypatch.setattr(email, "get_settings", lambda: SimpleNamespace(**{**base, **kw}))


def test_desarrollo_pasan_todos(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, environment="development")
    assert email.destinatarios_permitidos(TODOS) == TODOS


def test_produccion_omite_ficticios(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    assert email.destinatarios_permitidos(TODOS) == ["ana@gmail.com", "Dueño@Empresa.co"]


def test_demo_solo_lista_permitida(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, demo_mode=True, smtp_demo_recipients=" dueño@empresa.co , otro@x.com")
    assert email.destinatarios_permitidos(TODOS) == ["Dueño@Empresa.co"]


def test_demo_sin_lista_no_envia_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, demo_mode=True)
    assert email.destinatarios_permitidos(TODOS) == []


def test_send_email_sin_destinatarios_no_conecta(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, demo_mode=True, smtp_from="a <a@b.co>", smtp_host="smtp.invalido", smtp_port=587)

    def explotar(*_: object, **__: object) -> None:
        raise AssertionError("no debía abrir conexión SMTP")

    monkeypatch.setattr(email.smtplib, "SMTP", explotar)
    email.send_email(["admin@lospinos.demo"], "Asunto", "texto", "<p>html</p>", demo=False)


def test_conjunto_demo_sin_modo_demo_global(monkeypatch: pytest.MonkeyPatch) -> None:
    """La app real (DEMO_MODE apagado) escribe a todos; un conjunto de ejemplo solo a la lista permitida."""
    _settings(monkeypatch, smtp_demo_recipients="dueño@empresa.co")
    assert email.destinatarios_permitidos(TODOS) == ["ana@gmail.com", "Dueño@Empresa.co"]
    assert email.destinatarios_permitidos(TODOS, demo=True) == ["Dueño@Empresa.co"]


def test_sentry_no_envia_datos_sensibles() -> None:
    from app.core.observabilidad import depurar_evento

    evento = {
        "request": {
            "url": "https://app.test/api/v1/auth/enlace?token=SECRETO123&otro=1",
            "query_string": "token=SECRETO123&X-Amz-Signature=FIRMA",
            "headers": {"Authorization": "Bearer abc", "Cookie": "ph_token=x", "User-Agent": "Chrome"},
            "cookies": {"ph_token": "x"},
            "data": {"password": "Clave-Secreta"},
        },
        "user": {"email": "alguien@correo.co"},
    }
    limpio = str(depurar_evento(evento))
    for secreto in ("SECRETO123", "FIRMA", "Bearer abc", "ph_token=x", "Clave-Secreta", "alguien@correo.co"):
        assert secreto not in limpio, secreto
    assert "Chrome" in limpio and "otro=1" in limpio
