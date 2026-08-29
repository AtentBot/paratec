"""Camada de acesso ao catálogo Paratec (consultas ao Postgres).

Funções puras reutilizáveis; as ferramentas do agente (tools.py) são finas
por cima destas.
"""
from .db import query


def _variants_of(product_id: int) -> list[dict]:
    return query(
        """SELECT sku, material, dimensions, attributes, description
             FROM product_variants WHERE product_id = %s ORDER BY sku""",
        (product_id,),
    )


def buscar_produtos(termo: str, limite: int = 8) -> list[dict]:
    """Busca produtos por texto no título, SKU ou descrição das variantes."""
    like = f"%{termo}%"
    rows = query(
        """
        SELECT DISTINCT p.id, p.title, p.slug, p.source_url
          FROM products p
          LEFT JOIN product_variants v ON v.product_id = p.id
         WHERE p.title ILIKE %s
            OR p.description ILIKE %s
            OR v.sku ILIKE %s
            OR v.description ILIKE %s
            OR v.material ILIKE %s
         ORDER BY p.title
         LIMIT %s
        """,
        (like, like, like, like, like, limite),
    )
    for r in rows:
        r["variantes"] = _variants_of(r["id"])
    return rows


def detalhes_produto(identificador: str) -> dict | None:
    """Detalhes completos de um produto por slug ou id."""
    if identificador.isdigit():
        rows = query("SELECT * FROM products WHERE id = %s", (int(identificador),))
    else:
        rows = query("SELECT * FROM products WHERE slug = %s", (identificador,))
    if not rows:
        return None
    p = rows[0]
    p["variantes"] = _variants_of(p["id"])
    p["categorias"] = [
        c["name"]
        for c in query(
            """SELECT c.name FROM categories c
                 JOIN product_categories pc ON pc.category_id = c.id
                WHERE pc.product_id = %s""",
            (p["id"],),
        )
    ]
    return p


def buscar_por_sku(sku: str) -> list[dict]:
    """Localiza variante(s) por código SKU (tolera espaço/hífen: PRT101 = PRT-101)."""
    norm = sku.upper().replace(" ", "").replace("-", "")
    rows = query(
        """
        SELECT v.sku, v.material, v.dimensions, v.attributes, v.description,
               p.title AS produto, p.slug, p.source_url
          FROM product_variants v
          JOIN products p ON p.id = v.product_id
         WHERE replace(replace(upper(v.sku),' ',''),'-','') = %s
        """,
        (norm,),
    )
    return rows


def listar_categorias() -> list[dict]:
    return query(
        """SELECT c.name, count(pc.product_id) AS n_produtos
             FROM categories c
             LEFT JOIN product_categories pc ON pc.category_id = c.id
            GROUP BY c.name ORDER BY c.name"""
    )


def listar_produtos(
    termo: str | None = None,
    categoria: str | None = None,
    limite: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Lista produtos (com contagem de variantes) para a tela adm.

    Filtra por texto (`termo`) e/ou `categoria` quando informados; pagina via
    `limite`/`offset`. Cada item traz `n_variantes` e a lista `categorias`.
    """
    where, params = [], []
    if termo:
        like = f"%{termo}%"
        where.append(
            "(p.title ILIKE %s OR p.description ILIKE %s OR EXISTS ("
            " SELECT 1 FROM product_variants v WHERE v.product_id = p.id"
            " AND (v.sku ILIKE %s OR v.description ILIKE %s OR v.material ILIKE %s)))"
        )
        params += [like, like, like, like, like]
    if categoria:
        where.append(
            "EXISTS (SELECT 1 FROM product_categories pc JOIN categories c"
            " ON c.id = pc.category_id WHERE pc.product_id = p.id AND c.name ILIKE %s)"
        )
        params.append(f"%{categoria}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = query(
        f"""
        SELECT p.id, p.title, p.slug, p.source_url,
               (SELECT count(*) FROM product_variants v WHERE v.product_id = p.id)
                   AS n_variantes
          FROM products p
          {clause}
         ORDER BY p.title
         LIMIT %s OFFSET %s
        """,
        (*params, limite, offset),
    )
    for r in rows:
        r["categorias"] = [
            c["name"]
            for c in query(
                """SELECT c.name FROM categories c
                     JOIN product_categories pc ON pc.category_id = c.id
                    WHERE pc.product_id = %s ORDER BY c.name""",
                (r["id"],),
            )
        ]
    return rows


def contar_totais() -> dict:
    """Totais do catálogo para os cards do dashboard."""
    return query(
        """
        SELECT
          (SELECT count(*) FROM products)         AS produtos,
          (SELECT count(*) FROM product_variants) AS variantes,
          (SELECT count(*) FROM categories)       AS categorias
        """
    )[0]


def produtos_por_categoria(categoria: str, limite: int = 20) -> list[dict]:
    return query(
        """SELECT p.title, p.slug, p.source_url
             FROM products p
             JOIN product_categories pc ON pc.product_id = p.id
             JOIN categories c ON c.id = pc.category_id
            WHERE c.name ILIKE %s
            ORDER BY p.title LIMIT %s""",
        (f"%{categoria}%", limite),
    )
