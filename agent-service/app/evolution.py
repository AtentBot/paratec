"""Cliente mínimo da Evolution API (WhatsApp) para envio de saída pelo painel.

Só é usado quando EVOLUTION_API_URL/EVOLUTION_API_KEY estão configurados
(settings.evolution_configured). Envia texto para um número via a instância.
"""
from __future__ import annotations

import httpx

from .settings import settings


class EvolutionError(RuntimeError):
    pass


def enviar_texto(telefone: str, texto: str) -> dict:
    """Envia uma mensagem de texto pelo WhatsApp (Evolution API v2).

    `telefone` = número no formato aceito pela instância (ex: 5511999998888).
    Lança EvolutionError se não configurado ou se a API responder com erro.
    """
    if not settings.evolution_configured:
        raise EvolutionError("Evolution API não configurada (EVOLUTION_API_URL/KEY).")

    url = f"{settings.evolution_api_url.rstrip('/')}/message/sendText/{settings.evolution_instance}"
    try:
        resp = httpx.post(
            url,
            headers={"apikey": settings.evolution_api_key, "Content-Type": "application/json"},
            json={"number": telefone, "text": texto},
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise EvolutionError(f"falha de rede ao chamar a Evolution: {e}") from e

    if resp.status_code >= 400:
        raise EvolutionError(f"Evolution respondeu {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}
