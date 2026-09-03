"""Agente de atendimento da Paratec (LangGraph) — AGENTE ÚNICO.

Um único react agent com todas as ferramentas (cadastro, catálogo, pedidos,
entrega, boletos). Substitui a antiga malha supervisor+especialistas, que
quebrava com o Gemini 3.x: as ferramentas de handoff do langgraph-supervisor
(transfer_*) não preservam as "thought signatures" exigidas pelo Gemini 3,
gerando 400 INVALID_ARGUMENT. O agente único evita isso e é mais rápido
(menos chamadas ao LLM por mensagem).
"""
import logging
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from . import store
from .settings import settings
from .tools import (
    BOLETOS_TOOLS,
    CADASTRO_TOOLS,
    CATALOG_TOOLS,
    ENTREGA_TOOLS,
    PEDIDOS_TOOLS,
)

log = logging.getLogger("paratec.agents")

# Todas as ferramentas em um só agente.
ALL_TOOLS = CADASTRO_TOOLS + CATALOG_TOOLS + PEDIDOS_TOOLS + ENTREGA_TOOLS + BOLETOS_TOOLS

# Ferramenta de handoff -> (tipo na fila humana, nome do argumento com o resumo)
FILA_TOOLS = {
    "registrar_pedido": ("pedido", "resumo"),
    "consultar_entrega": ("entrega", "identificador"),
    "segunda_via_boleto": ("boleto", "identificador"),
}

# Ferramenta -> especialista (para as métricas do dashboard).
TOOL_ESPECIALISTA = {
    "verificar_cliente": "cadastro", "cadastrar_cliente": "cadastro",
    "buscar_produtos": "produtos", "detalhes_produto": "produtos",
    "buscar_por_sku": "produtos", "listar_categorias": "produtos",
    "produtos_por_categoria": "produtos",
    "registrar_pedido": "pedidos", "consultar_entrega": "entrega",
    "segunda_via_boleto": "boletos",
}

MARCA = (
    "A Paratec fabrica sistemas de Proteção contra Descargas Atmosféricas "
    "(SPDA / para-raios), conforme a NBR 5419. Atendimento via WhatsApp: "
    "responda SEMPRE em português do Brasil, cordial, objetivo e conciso. "
    "A empresa trabalha com ORÇAMENTO (não há preços)."
)

ATENDENTE_PROMPT = f"""\
Você é o atendente virtual da Paratec no WhatsApp. {MARCA}

CADASTRO (obrigatório antes de atender): no início da conversa, chame
verificar_cliente (o número do cliente é automático — NUNCA peça o telefone).
- Se NÃO for cadastrado: explique cordialmente que, para atender, é preciso um
  cadastro rápido e colete UM campo por vez, de forma natural: razão social,
  CNPJ, e-mail e nome do contato. A cada dado, chame cadastrar_cliente (pode ser
  incremental). Se CNPJ/e-mail vier inválido, peça a correção gentilmente. Só
  depois do cadastro completo (status 'ativo') prossiga para produtos/pedidos.
- Se JÁ for cadastrado: cumprimente pelo nome e atenda normalmente.

PRODUTOS: use as ferramentas de catálogo (buscar_produtos, detalhes_produto,
buscar_por_sku, listar_categorias, produtos_por_categoria). NUNCA invente
produtos, códigos ou especificações; se não achar, diga que vai verificar com a
equipe. Ao citar um produto, informe o(s) SKU(s) e material/dimensão.

PEDIDOS/ORÇAMENTOS: colete produto/SKU, quantidade e cidade/UF e registre com
registrar_pedido. Deixe claro que um vendedor dará sequência.

ENTREGA: use consultar_entrega com o número do pedido. Se indisponível, explique
que um atendente humano dará sequência.

BOLETOS: use segunda_via_boleto. Se indisponível, explique que o financeiro/
atendente humano dará sequência."""


@lru_cache(maxsize=1)
def _llm() -> ChatGoogleGenerativeAI:
    # resposta enxuta p/ WhatsApp
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.google_api_key,
        max_output_tokens=2048,
        temperature=1,
    )


@lru_cache(maxsize=1)
def _checkpointer():
    """Memória da conversa por thread.

    Padrão = MemorySaver (em processo): robusto, sem dependência de banco no
    caminho crítico da resposta — a durabilidade do histórico fica nas tabelas
    (store). PostgresSaver é OPCIONAL via LLM checkpointer=postgres (só quando
    o pool estiver estável; hoje o Postgres fechava a conexão no meio da query)."""
    from langgraph.checkpoint.memory import MemorySaver

    if settings.checkpointer.lower() == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                settings.pg_dsn,
                kwargs={"autocommit": True},
                min_size=1,
                max_size=3,
                check=ConnectionPool.check_connection,  # revalida conexões antes de usar
                open=True,
            )
            cp = PostgresSaver(pool)
            cp.setup()
            log.info("checkpointer: PostgresSaver ativo")
            return cp
        except Exception as e:  # pragma: no cover
            log.warning("checkpointer: PostgresSaver indisponível (%s); usando MemorySaver", e)

    return MemorySaver()


@lru_cache(maxsize=1)
def get_app():
    """Compila o agente único de atendimento (lazy)."""
    return create_react_agent(
        _llm(), ALL_TOOLS, prompt=ATENDENTE_PROMPT, checkpointer=_checkpointer()
    )


def _extrair_texto(content) -> str:
    """Normaliza o `content` da mensagem do agente para texto puro.

    Modelos Gemini 3.x (langchain-google-genai) podem devolver o conteúdo como
    LISTA de blocos ({'type': 'text', 'text': ...}) em vez de string — é preciso
    concatenar os trechos de texto para enviar ao WhatsApp."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        partes = []
        for bloco in content:
            if isinstance(bloco, dict):
                t = bloco.get("text")
                if t:
                    partes.append(t)
            elif isinstance(bloco, str):
                partes.append(bloco)
        return "\n".join(partes).strip()
    return str(content)


def _analisar(messages) -> dict:
    """Extrai do resultado: especialista (inferido pela ferramenta usada) e
    intenções de fila (chamadas às ferramentas de handoff, com o resumo)."""
    routed: str | None = None
    filas: list[tuple[str, str]] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            tool = tc.get("name") if isinstance(tc, dict) else None
            if not tool:
                continue
            if tool in TOOL_ESPECIALISTA:
                routed = TOOL_ESPECIALISTA[tool]
            if tool in FILA_TOOLS:
                tipo, arg = FILA_TOOLS[tool]
                args = tc.get("args", {}) if isinstance(tc, dict) else {}
                resumo = str(args.get(arg) or "").strip() or f"{tipo} sem detalhes"
                filas.append((tipo, resumo))
    return {"routed": routed, "filas": filas}


def responder(
    mensagem: str,
    thread_id: str,
    cliente: str | None = None,
    telefone: str | None = None,
) -> str:
    """Processa uma mensagem do cliente, PERSISTE o atendimento e devolve o texto.

    `thread_id` mantém o histórico (ex: número do WhatsApp). A persistência é
    best-effort: uma falha de banco nunca impede a resposta ao cliente.
    """
    try:
        store.upsert_conversation(thread_id, cliente, telefone)
        store.add_message(thread_id, "cliente", mensagem)
        store.log_event("mensagem_recebida", thread_id=thread_id)
    except Exception as e:  # pragma: no cover
        log.warning("persistência (entrada) falhou: %s", e)

    result = get_app().invoke(
        {"messages": [{"role": "user", "content": mensagem}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    resposta = _extrair_texto(result["messages"][-1].content)

    try:
        info = _analisar(result["messages"])
        routed = info["routed"]
        store.add_message(thread_id, "agente", resposta, especialista=routed)
        store.log_event("resposta_enviada", thread_id=thread_id, especialista=routed)
        if routed:
            store.log_event("roteou_especialista", thread_id=thread_id, especialista=routed)
        for tipo, resumo in info["filas"]:
            store.add_queue_item(
                tipo, resumo, thread_id=thread_id, cliente=cliente, telefone=telefone
            )
            store.log_event("fila_criada", thread_id=thread_id, especialista=routed,
                            meta={"tipo": tipo})
        if info["filas"]:
            store.set_status(thread_id, "humano")
            store.log_event("handoff_humano", thread_id=thread_id, especialista=routed)
        # Reflete o cadastro na conversa (nome exibido na tela adm).
        cust = store.get_customer(thread_id)
        if cust and cust.get("razao_social"):
            store.upsert_conversation(thread_id, cliente=cust["razao_social"])
    except Exception as e:  # pragma: no cover
        log.warning("persistência (saída) falhou: %s", e)

    return resposta
