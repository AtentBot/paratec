"""Ingestão self-serve de catálogo por tenant (upload de CSV/planilha).

Cada tenant importa o próprio catálogo. O produto é identificado pelo `slug`
(derivado do título) dentro do tenant — reimportar atualiza em vez de duplicar.
Ids de produto vêm da sequência `catalog_product_id_seq` (piso alto, acima dos
ids do WordPress da Paratec), então products.id segue PK global sem colisão.

Formato do CSV (cabeçalho, uma LINHA por variante/SKU; produtos com várias
variantes repetem o nome do produto em várias linhas):

    produto,categoria,sku,material,dimensoes,atributos,descricao

- `produto`   (obrigatório) nome do produto (agrupa as variantes)
- `categoria` (opcional) uma categoria por linha; várias linhas = várias categorias
- demais campos (opcionais) descrevem a variante/SKU
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata

from .db import get_pool

CSV_COLUNAS = ["produto", "categoria", "sku", "material", "dimensoes", "atributos", "descricao"]

# aceita variações de acento/caixa no cabeçalho
_ALIASES = {
    "produto": "produto", "nome": "produto", "titulo": "produto", "título": "produto",
    "categoria": "categoria", "categorias": "categoria",
    "sku": "sku", "codigo": "sku", "código": "sku",
    "material": "material",
    "dimensoes": "dimensoes", "dimensões": "dimensoes", "dimensao": "dimensoes", "dimensão": "dimensoes",
    "atributos": "atributos", "atributo": "atributos",
    "descricao": "descricao", "descrição": "descricao", "desc": "descricao",
}


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "produto"


def modelo_csv() -> str:
    """CSV de exemplo (template) para o usuário baixar e preencher."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUNAS)
    w.writerow(["Cabo flexível 2,5mm²", "Cabos", "CAB-25-PT", "Cobre", "100m", "Preto", "750V"])
    w.writerow(["Cabo flexível 2,5mm²", "Cabos", "CAB-25-AZ", "Cobre", "100m", "Azul", "750V"])
    w.writerow(["Disjuntor DIN 20A", "Proteção", "DIN-20", "", "", "Curva C", "Monopolar"])
    return buf.getvalue()


def _detectar_delimitador(texto: str) -> str:
    head = texto.splitlines()[0] if texto else ""
    return ";" if head.count(";") > head.count(",") else ","


def parse_csv(data: bytes) -> list[dict]:
    """Lê o CSV e agrupa por produto. Levanta ValueError em formato inválido."""
    texto = data.decode("utf-8-sig", errors="replace").strip()
    if not texto:
        raise ValueError("arquivo vazio")
    reader = csv.DictReader(io.StringIO(texto), delimiter=_detectar_delimitador(texto))
    if not reader.fieldnames:
        raise ValueError("não foi possível ler o cabeçalho do CSV")

    # normaliza os nomes das colunas
    campo = {}
    for raw in reader.fieldnames:
        chave = _ALIASES.get((raw or "").strip().lower())
        if chave:
            campo[raw] = chave
    if "produto" not in campo.values():
        raise ValueError("o CSV precisa de uma coluna 'produto'")

    produtos: dict[str, dict] = {}
    for linha in reader:
        vals = {campo[k]: (v or "").strip() for k, v in linha.items() if k in campo}
        titulo = vals.get("produto", "").strip()
        if not titulo:
            continue
        slug = slugify(titulo)
        p = produtos.setdefault(slug, {
            "titulo": titulo, "slug": slug, "categorias": [], "variantes": [],
        })
        cat = vals.get("categoria", "").strip()
        if cat and cat not in p["categorias"]:
            p["categorias"].append(cat)
        variante = {k: vals.get(k, "").strip() for k in ("sku", "material", "dimensoes", "atributos", "descricao")}
        if any(variante.values()):
            p["variantes"].append(variante)

    if not produtos:
        raise ValueError("nenhum produto encontrado no arquivo")
    return list(produtos.values())


def importar(tenant_id: int, produtos: list[dict]) -> dict:
    """Grava os produtos (upsert por slug) e suas variantes/categorias, numa
    única transação. Retorna contagens."""
    n_prod = n_var = 0
    cats_vistas: set[str] = set()
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            for p in produtos:
                # categorias do produto -> ids (upsert por tenant)
                cat_ids = []
                for nome in p["categorias"]:
                    cur.execute(
                        """INSERT INTO categories (tenant_id, name, slug) VALUES (%s, %s, %s)
                             ON CONFLICT (tenant_id, name) DO UPDATE SET slug = EXCLUDED.slug
                             RETURNING id""",
                        (tenant_id, nome, slugify(nome)),
                    )
                    cat_ids.append(cur.fetchone()["id"])
                    cats_vistas.add(nome)

                # produto (upsert por (tenant_id, slug); id novo vem da sequência)
                cur.execute(
                    """INSERT INTO products (id, tenant_id, slug, title, updated_at)
                         VALUES (nextval('catalog_product_id_seq'), %s, %s, %s, now())
                       ON CONFLICT (tenant_id, slug) DO UPDATE
                         SET title = EXCLUDED.title, updated_at = now()
                       RETURNING id""",
                    (tenant_id, p["slug"], p["titulo"]),
                )
                pid = cur.fetchone()["id"]
                n_prod += 1

                # recria vínculos de categoria e variantes (evita órfãos ao reimportar)
                cur.execute(
                    "DELETE FROM product_categories WHERE tenant_id = %s AND product_id = %s",
                    (tenant_id, pid),
                )
                for cid in cat_ids:
                    cur.execute(
                        """INSERT INTO product_categories (tenant_id, product_id, category_id)
                             VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                        (tenant_id, pid, cid),
                    )

                cur.execute(
                    "DELETE FROM product_variants WHERE tenant_id = %s AND product_id = %s",
                    (tenant_id, pid),
                )
                for v in p["variantes"]:
                    cur.execute(
                        """INSERT INTO product_variants
                             (tenant_id, product_id, sku, material, dimensions, attributes,
                              description, extracted_by)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, 'import')
                           ON CONFLICT (product_id, coalesce(sku,''),
                                        coalesce(dimensions,''), coalesce(attributes,''))
                           DO NOTHING""",
                        (tenant_id, pid, v["sku"] or None, v["material"] or None,
                         v["dimensoes"] or None, v["atributos"] or None, v["descricao"] or None),
                    )
                    n_var += 1
        conn.commit()
    return {"produtos": n_prod, "variantes": n_var, "categorias": len(cats_vistas)}


def limpar(tenant_id: int) -> dict:
    """Apaga TODO o catálogo do tenant (produtos em cascata + categorias)."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM products WHERE tenant_id = %s RETURNING id", (tenant_id,)
            )
            n = cur.rowcount
            cur.execute("DELETE FROM categories WHERE tenant_id = %s", (tenant_id,))
        conn.commit()
    return {"removidos": n}
