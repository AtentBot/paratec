"""Malha de agentes da Paratec (LangGraph) — arquitetura supervisor + especialistas.

Um SUPERVISOR roteia cada mensagem do cliente para o especialista adequado:
  - produtos  : catálogo, materiais, dimensões, códigos (SKU) — COMPLETO
  - pedidos   : registrar pedido/orçamento — stub (encaminha p/ humano)
  - entrega   : status de entrega        — stub (encaminha p/ humano)
  - boletos   : 2ª via de boleto          — stub (encaminha p/ humano)

Adicionar um novo especialista = criar um react agent com suas ferramentas e
incluí-lo na lista `especialistas` abaixo.
"""
import logging
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

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

ESPECIALISTAS = ("cadastro", "produtos", "pedidos", "entrega", "boletos")

# Ferramenta de handoff -> (tipo na fila humana, nome do argumento com o resumo)
FILA_TOOLS = {
    "registrar_pedido": ("pedido", "resumo"),
    "consultar_entrega": ("entrega", "identificador"),
    "segunda_via_boleto": ("boleto", "identificador"),
}

MARCA = (
    "A Paratec fabrica sistemas de Proteção contra Descargas Atmosféricas "
    "(SPDA / para-raios), conforme a NBR 5419. Atendimento via WhatsApp: "
    "responda SEMPRE em português do Brasil, cordial, objetivo e conciso. "
    "A empresa trabalha com ORÇAMENTO (não há preços)."
)

CADASTRO_PROMPT = f"""\
Você é o especialista de CADASTRO da Paratec. {MARCA}
No PRIMEIRO contato, use a ferramenta verificar_cliente (o número do cliente é
automático — NUNCA peça o telefone). Se já for cadastrado, cumprimente pelo nome
e diga que pode ajudar com o catálogo. Se NÃO for cadastrado, explique de forma
cordial que, para atender, é preciso um cadastro rápido, e colete UM campo por
vez, de forma natural: razão social, CNPJ, e-mail e nome do contato. A cada dado
recebido, chame cadastrar_cliente (pode ser incremental). Se o CNPJ ou e-mail
vier inválido, peça a correção gentilmente. Quando o cadastro ficar completo
(status 'ativo'), confirme e informe que agora ele pode consultar os produtos."""

PRODUTOS_PROMPT = f"""\
Você é o especialista de PRODUTOS da Paratec. {MARCA}
Use as ferramentas de catálogo para responder sobre produtos, materiais,
dimensões e códigos (SKU). NUNCA invente produtos, códigos ou especificações;
se não achar no catálogo, diga que vai verificar com a equipe. Ao citar um
produto, informe o(s) SKU(s) e material/dimensão relevantes."""

PEDIDOS_PROMPT = f"""\
Você é o especialista de PEDIDOS/ORÇAMENTOS da Paratec. {MARCA}
Colete produto/SKU, quantidade e cidade/UF e registre com a ferramenta.
Deixe claro que um vendedor dará sequência ao orçamento."""

ENTREGA_PROMPT = f"""\
Você é o especialista de ENTREGA da Paratec. {MARCA}
Peça o número do pedido e consulte o status. A integração ainda não está
disponível; nesse caso explique que um atendente humano dará sequência."""

BOLETOS_PROMPT = f"""\
Você é o especialista de BOLETOS da Paratec. {MARCA}
Ajude com 2ª via de boleto. A integração ainda não está disponível; nesse caso
explique que o financeiro/atendente humano dará sequência."""

SUPERVISOR_PROMPT = """\
Você é o supervisor do atendimento da Paratec (para-raios/SPDA) no WhatsApp.
REGRA DE CADASTRO (obrigatória): só clientes JÁ CADASTRADOS podem ser atendidos
por produtos/pedidos/entrega/boletos. Se você não tem certeza de que o cliente
está cadastrado, roteie para 'cadastro' PRIMEIRO — ele verifica e, se necessário,
faz o cadastro. Só depois de cadastrado, roteie para os demais.
Roteie cada mensagem para UM especialista:
- 'cadastro': verificar se o cliente é cadastrado e cadastrar clientes novos (razão social, CNPJ, e-mail, contato).
- 'produtos': catálogo, produtos, materiais, dimensões, códigos/SKU (apenas cadastrados).
- 'pedidos': fazer pedido, orçamento, cotação (apenas cadastrados).
- 'entrega': status/prazo/rastreio de pedido (apenas cadastrados).
- 'boletos': 2ª via de boleto, cobrança, financeiro (apenas cadastrados).
Não responda ao cliente diretamente; delegue. Responda sempre em português do Brasil."""


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
    """Persiste o estado do agente por thread. Usa PostgresSaver (durável entre
    reinícios); cai para MemorySaver se o Postgres/pacote não estiver disponível."""
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            settings.pg_dsn,
            kwargs={"autocommit": True},
            min_size=1,
            max_size=3,
            open=True,
        )
        cp = PostgresSaver(pool)
        cp.setup()
        log.info("checkpointer: PostgresSaver ativo")
        return cp
    except Exception as e:  # pragma: no cover - fallback de resiliência
        from langgraph.checkpoint.memory import MemorySaver

        log.warning("checkpointer: PostgresSaver indisponível (%s); usando MemorySaver", e)
        return MemorySaver()


@lru_cache(maxsize=1)
def get_app():
    """Compila a malha supervisor + especialistas (lazy)."""
    llm = _llm()
    especialistas = [
        create_react_agent(llm, CADASTRO_TOOLS, prompt=CADASTRO_PROMPT, name="cadastro"),
        create_react_agent(llm, CATALOG_TOOLS, prompt=PRODUTOS_PROMPT, name="produtos"),
        create_react_agent(llm, PEDIDOS_TOOLS, prompt=PEDIDOS_PROMPT, name="pedidos"),
        create_react_agent(llm, ENTREGA_TOOLS, prompt=ENTREGA_PROMPT, name="entrega"),
        create_react_agent(llm, BOLETOS_TOOLS, prompt=BOLETOS_PROMPT, name="boletos"),
    ]
    workflow = create_supervisor(
        especialistas,
        model=llm,
        prompt=SUPERVISOR_PROMPT,
    )
    return workflow.compile(checkpointer=_checkpointer())


def _analisar(messages) -> dict:
    """Extrai do resultado do grafo: especialista roteado e intenções de fila
    (chamadas às ferramentas de handoff, com o resumo do cliente)."""
    routed: str | None = None
    filas: list[tuple[str, str]] = []
    for m in messages:
        nome = getattr(m, "name", None)
        if nome in ESPECIALISTAS:
            routed = nome
        for tc in getattr(m, "tool_calls", None) or []:
            tool = tc.get("name") if isinstance(tc, dict) else None
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
    resposta = result["messages"][-1].content

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
