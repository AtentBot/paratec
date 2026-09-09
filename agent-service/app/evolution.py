"""Cliente mínimo da Evolution API (WhatsApp) para envio de saída pelo painel.

Só é usado quando EVOLUTION_API_URL/EVOLUTION_API_KEY estão configurados
(settings.evolution_configured). Envia texto para um número via a instância.

Também expõe as operações de GERENCIAMENTO de instância (criar/conectar/status/
desconectar/remover) usadas pela tela de Configurações do painel. Elas rodam com
a chave GLOBAL da Evolution que o agent-service guarda — assim o admin da Paratec
conecta um número novo (lê o QR Code) SEM nunca receber acesso à Evolution.
"""
from __future__ import annotations

import httpx

from .settings import settings

# Eventos que a Evolution deve entregar ao webhook de uma instância criada pelo
# painel — o suficiente para o fluxo do agente reagir a mensagens recebidas.
WEBHOOK_EVENTS = ["MESSAGES_UPSERT"]


class EvolutionError(RuntimeError):
    pass


def _base() -> str:
    return settings.evolution_api_url.rstrip("/")


def _headers() -> dict:
    return {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}


def _manage(method: str, path: str, *, json: dict | None = None) -> dict:
    """Chamada de gerenciamento à Evolution (usa a chave global). Devolve o JSON
    da resposta (ou {}). Lança EvolutionError se não configurado / em erro."""
    if not settings.evolution_configured:
        raise EvolutionError("Evolution API não configurada (EVOLUTION_API_URL/KEY).")
    try:
        resp = httpx.request(method, f"{_base()}{path}", headers=_headers(), json=json, timeout=30)
    except httpx.HTTPError as e:
        raise EvolutionError(f"falha de rede ao chamar a Evolution: {e}") from e
    if resp.status_code >= 400:
        raise EvolutionError(f"Evolution respondeu {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}


def enviar_texto(telefone: str, texto: str, instancia: str | None = None) -> dict:
    """Envia uma mensagem de texto pelo WhatsApp (Evolution API v2).

    `telefone` = número no formato aceito pela instância (ex: 5511999998888).
    `instancia` = número/instância de saída (default = settings.evolution_instance);
    no multi-agente, a resposta sai pela MESMA instância que recebeu a conversa.
    Lança EvolutionError se não configurado ou se a API responder com erro.
    """
    if not settings.evolution_configured:
        raise EvolutionError("Evolution API não configurada (EVOLUTION_API_URL/KEY).")

    inst = instancia or settings.evolution_instance
    url = f"{settings.evolution_api_url.rstrip('/')}/message/sendText/{inst}"
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


# --- Gerenciamento de instância (tela de Configurações) --------------------

def _norm_state(raw: str | None) -> str:
    """Normaliza o estado da conexão da Evolution para: conectado | conectando |
    desconectado. A Evolution usa 'open'/'connecting'/'close' (e variações)."""
    s = (raw or "").lower()
    if s in ("open", "connected"):
        return "conectado"
    if s in ("connecting", "qrcode", "pairing"):
        return "conectando"
    return "desconectado"


def _norm_numero(obj: dict) -> str | None:
    """Extrai o número/JID do dono da instância, quando disponível."""
    jid = obj.get("ownerJid") or obj.get("owner") or obj.get("number")
    if not jid:
        return None
    return str(jid).split("@", 1)[0].split(":", 1)[0]


def _norm_instancia(obj: dict) -> dict:
    """Normaliza uma instância vinda da Evolution (o formato varia por versão)."""
    inner = obj.get("instance") if isinstance(obj.get("instance"), dict) else obj
    nome = inner.get("instanceName") or inner.get("name") or obj.get("name")
    estado = _norm_state(
        inner.get("connectionStatus") or inner.get("state") or inner.get("status")
    )
    return {
        "nome": nome,
        "estado": estado,
        "numero": _norm_numero(inner) or _norm_numero(obj),
        "perfil": inner.get("profileName") or obj.get("profileName"),
    }


def _extrair_qr(data: dict) -> dict:
    """Extrai o QR Code / código de pareamento de uma resposta da Evolution."""
    qr = data.get("qrcode") if isinstance(data.get("qrcode"), dict) else data
    base64 = qr.get("base64")
    if base64 and not str(base64).startswith("data:"):
        base64 = f"data:image/png;base64,{base64}"
    return {
        "base64": base64,
        "code": qr.get("code"),
        "pairing_code": qr.get("pairingCode"),
    }


def listar_instancias() -> list[dict]:
    """Lista as instâncias existentes na Evolution (com estado de conexão)."""
    data = _manage("GET", "/instance/fetchInstances")
    itens = data if isinstance(data, list) else data.get("instances", [])
    return [_norm_instancia(i) for i in itens if isinstance(i, dict)]


def configurar_webhook(instancia: str) -> None:
    """Aponta o webhook da instância para o N8N (settings.evolution_webhook_url),
    para que as mensagens recebidas cheguem ao agente. No-op se não configurado."""
    if not settings.evolution_webhook_url:
        return
    _manage(
        "POST",
        f"/webhook/set/{instancia}",
        json={
            "webhook": {
                "enabled": True,
                "url": settings.evolution_webhook_url,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": WEBHOOK_EVENTS,
            }
        },
    )


def criar_instancia(instancia: str) -> dict:
    """Cria uma nova instância e devolve o QR Code inicial para pareamento.

    Se o webhook estiver configurado, já o aponta para o N8N (best-effort, para
    não travar a exibição do QR caso a rota de webhook varie entre versões)."""
    data = _manage(
        "POST",
        "/instance/create",
        json={"instanceName": instancia, "integration": "WHATSAPP-BAILEYS", "qrcode": True},
    )
    try:
        configurar_webhook(instancia)
    except EvolutionError:
        pass
    return _extrair_qr(data)


def conectar_instancia(instancia: str) -> dict:
    """(Re)obtém o QR Code / código de pareamento de uma instância existente."""
    return _extrair_qr(_manage("GET", f"/instance/connect/{instancia}"))


def status_instancia(instancia: str) -> dict:
    """Estado atual da conexão de uma instância (para o polling do painel)."""
    data = _manage("GET", f"/instance/connectionState/{instancia}")
    norm = _norm_instancia(data)
    norm["nome"] = norm["nome"] or instancia
    return norm


def desconectar_instancia(instancia: str) -> None:
    """Faz logout do WhatsApp na instância (o número se desconecta)."""
    _manage("DELETE", f"/instance/logout/{instancia}")


def remover_instancia(instancia: str) -> None:
    """Remove a instância da Evolution por completo."""
    _manage("DELETE", f"/instance/delete/{instancia}")


def enviar_midia(
    telefone: str,
    media_b64: str,
    *,
    mimetype: str,
    filename: str,
    caption: str = "",
    mediatype: str = "image",
    instancia: str | None = None,
) -> dict:
    """Envia uma mídia (imagem/banner) pelo WhatsApp (Evolution API v2).

    `media_b64` = conteúdo do arquivo em base64 (sem prefixo data:). Enviar o
    conteúdo (em vez de URL) evita depender de o serviço estar acessível
    publicamente pela Evolution. `caption` vira a legenda do banner.
    `instancia` = número/instância de saída (default = settings.evolution_instance).
    """
    if not settings.evolution_configured:
        raise EvolutionError("Evolution API não configurada (EVOLUTION_API_URL/KEY).")

    inst = instancia or settings.evolution_instance
    url = f"{settings.evolution_api_url.rstrip('/')}/message/sendMedia/{inst}"
    payload = {
        "number": telefone,
        "mediatype": mediatype,
        "mimetype": mimetype,
        "media": media_b64,
        "fileName": filename,
    }
    if caption:
        payload["caption"] = caption
    try:
        resp = httpx.post(
            url,
            headers={"apikey": settings.evolution_api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=60,  # mídia é maior que texto
        )
    except httpx.HTTPError as e:
        raise EvolutionError(f"falha de rede ao chamar a Evolution: {e}") from e

    if resp.status_code >= 400:
        raise EvolutionError(f"Evolution respondeu {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}
