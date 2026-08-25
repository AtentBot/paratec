"""Ferramentas expostas aos agentes LangGraph (finas sobre catalog.py)."""
import json

from langchain_core.tools import tool

from . import catalog


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
def buscar_produtos(termo: str) -> str:
    """Busca produtos no catálogo Paratec por palavra-chave (nome, material,
    aplicação ou código). Use para perguntas do tipo 'vocês têm captor Franklin?'
    ou 'preciso de conector bimetálico'. Retorna produtos e suas variantes/SKUs."""
    return _json(catalog.buscar_produtos(termo))


@tool
def detalhes_produto(identificador: str) -> str:
    """Retorna os detalhes completos de UM produto (todas as variantes, materiais,
    dimensões, descrição e categorias). Aceita o slug ou o id do produto,
    normalmente obtido antes via buscar_produtos."""
    p = catalog.detalhes_produto(identificador)
    return _json(p) if p else "Produto não encontrado."


@tool
def buscar_por_sku(sku: str) -> str:
    """Localiza uma variante pelo código SKU (ex: PRT-101, PRT780, SG2).
    Tolera variações de espaço/hífen. Use quando o cliente informar um código."""
    rows = catalog.buscar_por_sku(sku)
    return _json(rows) if rows else f"Nenhuma variante encontrada para o código {sku}."


@tool
def listar_categorias() -> str:
    """Lista as categorias de produtos da Paratec e quantos produtos há em cada uma.
    Use para orientar o cliente sobre as famílias disponíveis."""
    return _json(catalog.listar_categorias())


@tool
def produtos_por_categoria(categoria: str) -> str:
    """Lista os produtos de uma categoria (ex: 'Conectores de Uso Geral',
    'Condutor de Alumínio'). Use após listar_categorias ou quando o cliente
    citar uma família de produtos."""
    rows = catalog.produtos_por_categoria(categoria)
    return _json(rows) if rows else f"Nenhum produto na categoria '{categoria}'."


CATALOG_TOOLS = [
    buscar_produtos,
    detalhes_produto,
    buscar_por_sku,
    listar_categorias,
    produtos_por_categoria,
]


# ---------------------------------------------------------------------------
# Ferramentas dos especialistas ainda não integrados. Hoje coletam os dados
# e encaminham para atendimento humano; cada uma é o ponto de integração com
# o sistema de origem (ERP de pedidos, transportadora, financeiro/boletos).
# ---------------------------------------------------------------------------
@tool
def registrar_pedido(resumo: str) -> str:
    """Registra a intenção de pedido/orçamento do cliente (produto/SKU,
    quantidade, cidade/UF) para a equipe de vendas dar sequência.
    TODO: integrar com o ERP de pedidos."""
    return _json({
        "status": "encaminhado_humano",
        "resumo": resumo,
        "mensagem": "Pedido/orçamento registrado; um vendedor dará sequência.",
    })


@tool
def consultar_entrega(identificador: str) -> str:
    """Consulta o status de entrega de um pedido pelo número/identificador.
    TODO: integrar com a transportadora / módulo de logística."""
    return _json({
        "status": "indisponivel",
        "mensagem": "Consulta de entrega ainda não integrada; encaminhar para humano.",
    })


@tool
def segunda_via_boleto(identificador: str) -> str:
    """Emite/localiza a 2ª via de boleto do cliente (por CNPJ/pedido/nota).
    TODO: integrar com o sistema financeiro."""
    return _json({
        "status": "indisponivel",
        "mensagem": "2ª via de boleto ainda não integrada; encaminhar para humano.",
    })


PEDIDOS_TOOLS = [registrar_pedido]
ENTREGA_TOOLS = [consultar_entrega]
BOLETOS_TOOLS = [segunda_via_boleto]
