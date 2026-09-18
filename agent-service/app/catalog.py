"""Camada de acesso ao catálogo (consultas ao Postgres), isolada por tenant.

Funções puras reutilizáveis; as ferramentas do agente (tools.py) são finas
por cima destas. Toda consulta filtra por `tenant_id` (products.tenant_id) —
cada cliente vê apenas o próprio catálogo.
"""
from .db import query


def _variants_of(tenant_id: int, product_id: int) -> list[dict]:
    return query(
        """SELECT sku, material, dimensions, attributes, description
             FROM product_variants WHERE tenant_id = %s AND product_id = %s ORDER BY sku""",
        (tenant_id, product_id),
    )


def buscar_produtos(tenant_id: int, termo: str, limite: int = 8) -> list[dict]:
    """Busca produtos por texto no título, SKU ou descrição das variantes."""
    like = f"%{termo}%"
    rows = query(
        """
        SELECT DISTINCT p.id, p.title, p.slug, p.source_url
          FROM products p
          LEFT JOIN product_variants v ON v.product_id = p.id
         WHERE p.tenant_id = %s
           AND (p.title ILIKE %s
            OR p.description ILIKE %s
            OR v.sku ILIKE %s
            OR v.description ILIKE %s
            OR v.material ILIKE %s)
         ORDER BY p.title
         LIMIT %s
        """,
        (tenant_id, like, like, like, like, like, limite),
    )
    for r in rows:
        r["variantes"] = _variants_of(tenant_id, r["id"])
    return rows


def detalhes_produto(tenant_id: int, identificador: str) -> dict | None:
    """Detalhes completos de um produto por slug ou id (dentro do tenant)."""
    if identificador.isdigit():
        rows = query(
            "SELECT * FROM products WHERE tenant_id = %s AND id = %s",
            (tenant_id, int(identificador)),
        )
    else:
        rows = query(
            "SELECT * FROM products WHERE tenant_id = %s AND slug = %s",
            (tenant_id, identificador),
        )
    if not rows:
        return None
    p = rows[0]
    p["variantes"] = _variants_of(tenant_id, p["id"])
    p["categorias"] = [
        c["name"]
        for c in query(
            """SELECT c.name FROM categories c
                 JOIN product_categories pc ON pc.category_id = c.id
                WHERE pc.product_id = %s AND c.tenant_id = %s""",
            (p["id"], tenant_id),
        )
    ]
    return p


def buscar_por_sku(tenant_id: int, sku: str) -> list[dict]:
    """Localiza variante(s) por código SKU (tolera espaço/hífen: PRT101 = PRT-101)."""
    norm = sku.upper().replace(" ", "").replace("-", "")
    rows = query(
        """
        SELECT v.sku, v.material, v.dimensions, v.attributes, v.description,
               p.title AS produto, p.slug, p.source_url
          FROM product_variants v
          JOIN products p ON p.id = v.product_id
         WHERE p.tenant_id = %s
           AND replace(replace(upper(v.sku),' ',''),'-','') = %s
        """,
        (tenant_id, norm),
    )
    return rows


def listar_categorias(tenant_id: int) -> list[dict]:
    return query(
        """SELECT c.name, count(pc.product_id) AS n_produtos
             FROM categories c
             LEFT JOIN product_categories pc ON pc.category_id = c.id
            WHERE c.tenant_id = %s
            GROUP BY c.name ORDER BY c.name""",
        (tenant_id,),
    )


def listar_produtos(
    tenant_id: int,
    termo: str | None = None,
    categoria: str | None = None,
    limite: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Lista produtos (com contagem de variantes) para a tela adm.

    Filtra por texto (`termo`) e/ou `categoria` quando informados; pagina via
    `limite`/`offset`. Cada item traz `n_variantes` e a lista `categorias`.
    """
    where = ["p.tenant_id = %s"]
    params: list = [tenant_id]
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
    clause = "WHERE " + " AND ".join(where)
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
                    WHERE pc.product_id = %s AND c.tenant_id = %s ORDER BY c.name""",
                (r["id"], tenant_id),
            )
        ]
    return rows


def contar_totais(tenant_id: int) -> dict:
    """Totais do catálogo do tenant para os cards do dashboard."""
    return query(
        """
        SELECT
          (SELECT count(*) FROM products WHERE tenant_id=%s)         AS produtos,
          (SELECT count(*) FROM product_variants WHERE tenant_id=%s) AS variantes,
          (SELECT count(*) FROM categories WHERE tenant_id=%s)       AS categorias
        """,
        (tenant_id, tenant_id, tenant_id),
    )[0]


def produtos_por_categoria(tenant_id: int, categoria: str, limite: int = 20) -> list[dict]:
    return query(
        """SELECT p.title, p.slug, p.source_url
             FROM products p
             JOIN product_categories pc ON pc.product_id = p.id
             JOIN categories c ON c.id = pc.category_id
            WHERE p.tenant_id = %s AND c.name ILIKE %s
            ORDER BY p.title LIMIT %s""",
        (tenant_id, f"%{categoria}%", limite),
    )
