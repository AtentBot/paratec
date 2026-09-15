"""Mailer (SMTP): comportamento sem configuração (puro, sem rede)."""
from app import mailer
from app.settings import settings


def test_email_disabled_e_noop(monkeypatch):
    # Sem SMTP configurado: email_enabled=False e enviar() é no-op silencioso.
    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(settings, "smtp_from_email", "", raising=False)
    assert settings.email_enabled is False

    chamou = {"v": False}
    monkeypatch.setattr(mailer, "_send_sync", lambda *a, **k: chamou.__setitem__("v", True))
    mailer.enviar("x@y.com", "assunto", "corpo")  # não deve disparar thread/_send_sync
    assert chamou["v"] is False


def test_email_enabled_flag_e_reply_to(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "mail.exemplo.com", raising=False)
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@exemplo.com", raising=False)
    monkeypatch.setattr(settings, "smtp_reply_to", "", raising=False)
    monkeypatch.setattr(settings, "support_email", "contato@exemplo.com", raising=False)
    assert settings.email_enabled is True
    assert settings.reply_to == "contato@exemplo.com"  # cai no support_email
