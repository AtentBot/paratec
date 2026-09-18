"""Injeção de fórmula (CSV/DDE): campos vindos do cliente (razão social, resumo)
não podem sair como fórmula viva no export."""
import csv
import io

from app.main import _csv, _csv_celula


def test_celula_neutraliza_gatilhos_de_formula():
    for g in ("=", "+", "-", "@", "|", "\t", "\r"):
        assert _csv_celula(g + "cmd").startswith("'"), f"{g!r} deveria ser prefixado"
    # valor comum não é tocado
    assert _csv_celula("ACME Ltda") == "ACME Ltda"
    assert _csv_celula("") == ""
    assert _csv_celula(123) == 123  # não-string passa direto


def test_export_csv_nao_emite_formula_viva():
    linhas = [{
        "razao_social": '=HYPERLINK("http://evil","x")',
        "resumo": '=cmd|\'/c calc\'!A1',
        "nome_contato": "@SUM(1)",
        "ok": "Loja do João",
    }]
    cols = ["razao_social", "resumo", "nome_contato", "ok"]
    body = _csv("x.csv", cols, linhas).body.decode()
    dados = list(csv.reader(io.StringIO(body)))[1]
    assert all(c[:1] not in "=+-@|\t\r" for c in dados), "nenhuma célula pode iniciar com gatilho"
    assert dados[3] == "Loja do João", "valor legítimo deve ficar intacto"
