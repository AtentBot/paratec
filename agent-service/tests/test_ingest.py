"""Ingestão self-serve de catálogo: parse do CSV (puro) + isolamento por tenant."""
import pytest

from app import ingest
from .conftest import requires_db

# CSV com ';' (evita ambiguidade da vírgula no nome "2,5mm"). str -> encode UTF-8
# (byte-literal não aceita caracteres não-ASCII como o "ç" de Proteção).
CSV_PV = (
    "produto;categoria;sku;material;dimensoes;atributos;descricao\n"
    "Cabo 2,5mm;Cabos;CAB-25-PT;Cobre;100m;Preto;750V\n"
    "Cabo 2,5mm;Cabos;CAB-25-AZ;Cobre;100m;Azul;750V\n"
    "Disjuntor 20A;Proteção;DIN-20;;;Curva C;Monopolar\n"
).encode("utf-8")


def test_parse_agrupa_por_produto_e_delimitador_pv():
    prods = ingest.parse_csv(CSV_PV)
    por_slug = {p["slug"]: p for p in prods}
    assert set(por_slug) == {"cabo-2-5mm", "disjuntor-20a"}
    cabo = por_slug["cabo-2-5mm"]
    assert cabo["categorias"] == ["Cabos"]
    assert {v["sku"] for v in cabo["variantes"]} == {"CAB-25-PT", "CAB-25-AZ"}
    disj = por_slug["disjuntor-20a"]
    assert disj["variantes"][0]["atributos"] == "Curva C"


def test_parse_erros():
    with pytest.raises(ValueError):
        ingest.parse_csv(b"")
    with pytest.raises(ValueError):
        ingest.parse_csv(b"coluna_errada,outra\n1,2\n")  # sem coluna 'produto'


@requires_db
def test_importar_isola_por_tenant(db):
    from app import catalog

    a = int((db.get_tenant_by_slug("ing-a") or db.create_tenant("ing-a", "Ing A"))["id"])
    b = int((db.get_tenant_by_slug("ing-b") or db.create_tenant("ing-b", "Ing B"))["id"])
    ingest.limpar(a)
    ingest.limpar(b)

    ra = ingest.importar(a, ingest.parse_csv(CSV_PV))
    assert ra["produtos"] == 2 and ra["variantes"] == 3

    # tenant B recebe um catálogo diferente
    ingest.importar(b, ingest.parse_csv(
        b"produto;categoria;sku\nMangueira;Hidraulica;MANG-1\n"
    ))

    titulos_a = {p["title"] for p in catalog.listar_produtos(a)}
    titulos_b = {p["title"] for p in catalog.listar_produtos(b)}
    assert "Cabo 2,5mm" in titulos_a and "Mangueira" not in titulos_a
    assert titulos_b == {"Mangueira"}

    # reimportar NÃO duplica (upsert por slug)
    ingest.importar(a, ingest.parse_csv(CSV_PV))
    assert len([p for p in catalog.listar_produtos(a)]) == 2

    # limpar zera só o tenant A
    ingest.limpar(a)
    assert catalog.listar_produtos(a) == []
    assert {p["title"] for p in catalog.listar_produtos(b)} == {"Mangueira"}
