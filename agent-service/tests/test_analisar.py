"""Testa a extração de roteamento e intenções de fila do resultado do grafo.
Puro (sem DB, sem LLM) — sempre roda."""
from types import SimpleNamespace

from app.agents import _analisar, _extrair_texto


def _msg(name=None, tool_calls=None):
    return SimpleNamespace(name=name, tool_calls=tool_calls or [])


def test_detecta_especialista_roteado():
    msgs = [
        _msg(name="supervisor"),
        _msg(name="produtos"),
    ]
    info = _analisar(msgs)
    assert info["routed"] == "produtos"
    assert info["filas"] == []


def test_pedido_gera_intencao_de_fila():
    msgs = [
        _msg(name="pedidos"),
        _msg(tool_calls=[{"name": "registrar_pedido", "args": {"resumo": "20 hastes"}}]),
    ]
    info = _analisar(msgs)
    assert info["routed"] == "pedidos"
    assert info["filas"] == [("pedido", "20 hastes")]


def test_entrega_e_boleto_mapeiam_tipo():
    msgs = [
        _msg(tool_calls=[{"name": "consultar_entrega", "args": {"identificador": "4471"}}]),
        _msg(tool_calls=[{"name": "segunda_via_boleto", "args": {"identificador": "NF-90"}}]),
    ]
    filas = dict(_analisar(msgs)["filas"])
    assert filas == {"entrega": "4471", "boleto": "NF-90"}


def test_resumo_vazio_tem_fallback():
    msgs = [_msg(tool_calls=[{"name": "registrar_pedido", "args": {}}])]
    assert _analisar(msgs)["filas"] == [("pedido", "pedido sem detalhes")]


def test_extrair_texto_string():
    assert _extrair_texto("olá") == "olá"


def test_extrair_texto_blocos_gemini3():
    # Formato real do gemini-flash-latest (Gemini 3.x) via langchain-google-genai.
    content = [{"type": "text", "text": "Sim, fabricamos.", "extras": {"signature": "x"}}]
    assert _extrair_texto(content) == "Sim, fabricamos."


def test_extrair_texto_blocos_multiplos():
    content = [{"text": "linha 1"}, {"text": "linha 2"}, {"type": "thought"}]
    assert _extrair_texto(content) == "linha 1\nlinha 2"


def test_ignora_ferramentas_de_catalogo():
    msgs = [
        _msg(name="produtos"),
        _msg(tool_calls=[{"name": "buscar_produtos", "args": {"termo": "captor"}}]),
    ]
    assert _analisar(msgs)["filas"] == []
