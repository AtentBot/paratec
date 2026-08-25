"""Malha de agentes da Paratec (LangGraph) — arquitetura supervisor + especialistas.

Um SUPERVISOR roteia cada mensagem do cliente para o especialista adequado:
  - produtos  : catálogo, materiais, dimensões, códigos (SKU) — COMPLETO
  - pedidos   : registrar pedido/orçamento — stub (encaminha p/ humano)
  - entrega   : status de entrega        — stub (encaminha p/ humano)
  - boletos   : 2ª via de boleto          — stub (encaminha p/ humano)

Adicionar um novo especialista = criar um react agent com suas ferramentas e
incluí-lo na lista `especialistas` abaixo.
"""
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

from .settings import settings
from .tools import (
    BOLETOS_TOOLS,
    CATALOG_TOOLS,
    ENTREGA_TOOLS,
    PEDIDOS_TOOLS,
)

MARCA = (
    "A Paratec fabrica sistemas de Proteção contra Descargas Atmosféricas "
    "(SPDA / para-raios), conforme a NBR 5419. Atendimento via WhatsApp: "
    "responda SEMPRE em português do Brasil, cordial, objetivo e conciso. "
    "A empresa trabalha com ORÇAMENTO (não há preços)."
)

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
Roteie cada mensagem do cliente para UM especialista:
- 'produtos': dúvidas sobre catálogo, produtos, materiais, dimensões, códigos/SKU, o que a empresa vende.
- 'pedidos': fazer pedido, pedir orçamento, comprar, cotação.
- 'entrega': status/prazo de entrega, rastreio de um pedido existente.
- 'boletos': 2ª via de boleto, cobrança, financeiro.
Se ambíguo, prefira 'produtos'. Não responda ao cliente diretamente; delegue.
Responda sempre em português do Brasil."""


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
def get_app():
    """Compila a malha supervisor + especialistas (lazy, memória por thread)."""
    llm = _llm()
    especialistas = [
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
    return workflow.compile(checkpointer=MemorySaver())


def responder(mensagem: str, thread_id: str) -> str:
    """Processa uma mensagem do cliente e devolve a resposta em texto.

    `thread_id` mantém o histórico da conversa (ex: número do WhatsApp).
    """
    result = get_app().invoke(
        {"messages": [{"role": "user", "content": mensagem}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content
