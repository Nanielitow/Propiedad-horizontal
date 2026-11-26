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
    email.send_email(["admin@lospinos.demo"], "Asunto", "texto", "<p>html</p>")
