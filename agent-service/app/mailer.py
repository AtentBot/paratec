"""Envio de e-mail (SMTP) para notificações — hoje: chamados de suporte.

Best-effort e assíncrono (thread daemon): uma falha de SMTP nunca quebra o
fluxo do painel. Desabilitado quando SMTP não está configurado (email_enabled).
As credenciais vêm do ambiente (settings.smtp_*); NUNCA commitar SMTP_PASS.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from .settings import settings

log = logging.getLogger("atentbot.mailer")


def _h(v: str | None) -> str:
    """Neutraliza CR/LF em valores de cabeçalho (defense-in-depth contra header
    injection e para não deixar um assunto/e-mail com quebra silenciar o envio —
    a policy 'default' do email levantaria ValueError)."""
    return (v or "").replace("\r", " ").replace("\n", " ").strip()


def _send_sync(to: str, subject: str, body: str, reply_to: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = f"{_h(settings.smtp_from_name)} <{_h(settings.smtp_from_email)}>"
    msg["To"] = _h(to)
    msg["Subject"] = _h(subject)
    msg["Reply-To"] = _h(reply_to or settings.reply_to)
    msg.set_content(body)

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, 465,
                              context=ssl.create_default_context(), timeout=15) as s:
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_pass)
            s.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.ehlo()
            if settings.smtp_ssl:
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_pass)
            s.send_message(msg)


def enviar(to: str | None, subject: str, body: str, reply_to: str | None = None) -> None:
    """Envia um e-mail em background (best-effort). No-op se SMTP off ou sem destino."""
    if not settings.email_enabled or not to:
        return

    def run() -> None:
        try:
            _send_sync(to, subject, body, reply_to)
        except Exception as e:  # pragma: no cover
            log.warning("envio de e-mail falhou (%s): %s", subject, e)

    threading.Thread(target=run, name="email", daemon=True).start()


# --- Notificações de chamados de suporte ----------------------------------

def _painel_suporte() -> str:
    return f"{settings.panel_url.rstrip('/')}/suporte"


def notificar_novo_chamado(
    ticket: dict, tenant_nome: str | None, cliente_email: str | None, descricao: str
) -> None:
    """Avisa o suporte (e confirma ao cliente) sobre um chamado recém-aberto."""
    tid = ticket["id"]
    assunto = ticket["assunto"]
    corpo = (
        f"Novo chamado #{tid} — {assunto}\n\n"
        f"Cliente: {tenant_nome or '—'}\n"
        f"Aberto por: {cliente_email or '—'}\n"
        f"Categoria: {ticket.get('categoria')} · Prioridade: {ticket.get('prioridade')}\n\n"
        f"{descricao}\n\n"
        f"Abrir no painel: {_painel_suporte()}"
    )
    enviar(settings.reply_to, f"[AtentBot] Novo chamado #{tid} — {assunto}",
           corpo, reply_to=cliente_email)

    if cliente_email:
        enviar(
            cliente_email, f"[AtentBot] Recebemos seu chamado #{tid}",
            f"Olá! Recebemos seu chamado \"{assunto}\" (#{tid}). Nossa equipe "
            f"responderá em breve.\n\nAcompanhe em {_painel_suporte()}.",
        )


def notificar_nova_mensagem(
    ticket_id: int, assunto: str, tenant_nome: str | None, cliente_email: str | None, corpo: str
) -> None:
    """Avisa o suporte sobre uma nova mensagem do cliente num chamado."""
    texto = (
        f"Nova mensagem no chamado #{ticket_id} — {assunto}\n\n"
        f"Cliente: {tenant_nome or '—'} ({cliente_email or '—'})\n\n"
        f"{corpo}\n\nAbrir: {_painel_suporte()}"
    )
    enviar(settings.reply_to, f"[AtentBot] Nova mensagem no chamado #{ticket_id}",
           texto, reply_to=cliente_email)


# --- Conta ------------------------------------------------------------------

def enviar_verificacao_email(to: str, nome: str | None, link: str) -> None:
    """Link de confirmação do e-mail enviado no cadastro (e nos reenvios)."""
    saudacao = f"Olá, {nome}!" if nome else "Olá!"
    enviar(
        to, "[AtentBot] Confirme seu e-mail",
        f"{saudacao}\n\n"
        f"Para ativar sua conta no AtentBot, confirme seu e-mail pelo link abaixo:\n\n"
        f"{link}\n\n"
        f"O link vale por {settings.email_verification_ttl_hours} horas. "
        f"Depois da confirmação você valida seu WhatsApp, escolhe o plano e "
        f"cadastra o cartão para liberar o painel.\n\n"
        f"Se você não criou esta conta, ignore este e-mail.",
    )
