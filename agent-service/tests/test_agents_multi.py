"""Testes do multi-agente (persona + capacidades) — sem DB nem LLM."""
from app import agents
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _nomes(tools):
    return {t.name for t in tools}


def test_capacidades_selecionam_tools():
    # Só boletos: tem a tool de boleto + cadastro; NÃO tem catálogo.
    tools = agents._montar_tools(("boletos",))
    nomes = _nomes(tools)
    assert "segunda_via_boleto" in nomes
    assert "verificar_cliente" in nomes  # cadastro é sempre incluído
    assert "buscar_produtos" not in nomes


def test_prompt_inclui_persona_e_bloco_da_capacidade():
    prompt = agents._montar_prompt("Você é o setor Financeiro.", ("boletos",))
    assert "Financeiro" in prompt
    assert "BOLETOS" in prompt
    assert "PRODUTOS:" not in prompt  # capacidade de catálogo desligada


def test_agente_padrao_tem_todas_as_capacidades():
    tools = agents._montar_tools(agents.CAPACIDADES_PADRAO)
    nomes = _nomes(tools)
    assert {"buscar_produtos", "registrar_pedido", "segunda_via_boleto"} <= nomes


def test_endpoint_capacidades():
    r = client.get("/agentes/capacidades")
    assert r.status_code == 200
    chaves = {c["chave"] for c in r.json()}
    assert chaves == set(agents.CAPACIDADES_ORDEM)
