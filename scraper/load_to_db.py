#!/usr/bin/env python3
"""
Carrega data/products.json no Postgres (idempotente / upsert).

Uso:
  python scraper/load_to_db.py --schema     # aplica db/schema.sql antes
  python scraper/load_to_db.py              # so carrega os dados

Le a conexao das variaveis PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD (.env).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
load_dotenv(ROOT / ".env")


def dsn() -> str:
    return (
        f"host={os.environ['PGHOST']} port={os.environ.get('PGPORT', '5432')} "
        f"dbname={os.environ['PGDATABASE']} user={os.environ['PGUSER']} "
        f"password={os.environ['PGPASSWORD']}"
    )


def apply_schema(conn):
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("[ok] schema aplicado (db/schema.sql)")


def slugify(name: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def load(conn, products):
    with conn.cursor() as cur:
        # 1) categorias unicas
        cats = sorted({c for p in products for c in p["categories"]})
        cat_id = {}
        for name in cats:
            cur.execute(
                """INSERT INTO categories (name, slug) VALUES (%s, %s)
                   ON CONFLICT (name) DO UPDATE SET slug = EXCLUDED.slug
                   RETURNING id""",
                (name, slugify(name)),
            )
            cat_id[name] = cur.fetchone()[0]

        n_prod = n_var = 0
        for p in products:
            cur.execute(
                """INSERT INTO products
                     (id, slug, title, description, image_url, source_url,
                      featured, raw_text, wp_modified, updated_at)
                   VALUES (%(id)s,%(slug)s,%(title)s,%(description)s,%(image_url)s,
                           %(source_url)s,%(featured)s,%(raw_text)s,%(wp_modified)s, now())
                   ON CONFLICT (id) DO UPDATE SET
                     slug=EXCLUDED.slug, title=EXCLUDED.title,
                     description=EXCLUDED.description, image_url=EXCLUDED.image_url,
                     source_url=EXCLUDED.source_url, featured=EXCLUDED.featured,
                     raw_text=EXCLUDED.raw_text, wp_modified=EXCLUDED.wp_modified,
                     updated_at=now()""",
                p,
            )
            n_prod += 1

            # vinculos de categoria (reset e reinsere)
            cur.execute("DELETE FROM product_categories WHERE product_id=%s", (p["id"],))
            for c in p["categories"]:
                cur.execute(
                    """INSERT INTO product_categories (product_id, category_id)
                       VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    (p["id"], cat_id[c]),
                )

            # variantes: reset e reinsere (evita orfaos ao reprocessar)
            cur.execute("DELETE FROM product_variants WHERE product_id=%s", (p["id"],))
            for v in p["variants"]:
                cur.execute(
                    """INSERT INTO product_variants
                         (product_id, sku, material, dimensions, attributes,
                          description, raw_text, extracted_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (product_id, coalesce(sku,''),
                                    coalesce(dimensions,''), coalesce(attributes,''))
                       DO NOTHING""",
                    (p["id"], v.get("sku"), v.get("material"), v.get("dimensions"),
                     v.get("attributes"), v.get("description"), v.get("raw_text"),
                     v.get("extracted_by", "heuristic")),
                )
                n_var += 1
    conn.commit()
    return len(cats), n_prod, n_var


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="store_true", help="aplica db/schema.sql antes")
    args = ap.parse_args()

    pf = DATA / "products.json"
    if not pf.exists():
        sys.exit("data/products.json nao encontrado. Rode scraper/extract.py antes.")
    products = json.loads(pf.read_text(encoding="utf-8"))

    with psycopg.connect(dsn(), connect_timeout=15) as conn:
        if args.schema:
            apply_schema(conn)
        n_cat, n_prod, n_var = load(conn, products)
        print(f"[ok] carregado: {n_cat} categorias, {n_prod} produtos, {n_var} variantes")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM products")
            print("  total products na base:", cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM product_variants")
            print("  total variants na base:", cur.fetchone()[0])


if __name__ == "__main__":
    main()
