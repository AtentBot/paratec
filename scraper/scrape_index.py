#!/usr/bin/env python3
"""
Fase 1 do scraper do catalogo Paratec.

Enumera todos os produtos via API REST do WordPress (wp/v2/produto),
salva um indice estruturado (data/index.json) e baixa o HTML de cada
pagina de produto para data/raw/ (cache para reprocessar sem rebater o site).

Zero dependencias externas — roda com a stdlib do Python 3.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("PARATEC_BASE_URL", "https://paratec.com.br")
DELAY = float(os.environ.get("SCRAPE_DELAY_SECONDS", "0.5"))
PER_PAGE = 50
UA = "ParatecCatalogBot/1.0 (+internal catalog sync)"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"


def http_get(url: str, as_json: bool = False, retries: int = 3):
    """GET com retry simples. Retorna (body, headers)."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                headers = dict(resp.headers)
                if as_json:
                    return json.loads(body.decode("utf-8")), headers
                return body.decode("utf-8", errors="replace"), headers
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            wait = attempt * 2
            print(f"  ! tentativa {attempt} falhou ({e}); aguardando {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"GET falhou apos {retries} tentativas: {url} :: {last_err}")


def enumerate_products():
    """Percorre a API REST paginada e retorna a lista bruta de produtos."""
    products = []
    page = 1
    total_pages = None
    while True:
        url = (
            f"{BASE_URL}/wp-json/wp/v2/produto"
            f"?per_page={PER_PAGE}&page={page}&_embed=1"
        )
        print(f"-> API pagina {page}{'/' + str(total_pages) if total_pages else ''}")
        batch, headers = http_get(url, as_json=True)
        if total_pages is None:
            total_pages = int(headers.get("X-WP-TotalPages", "1"))
            total = headers.get("X-WP-Total", "?")
            print(f"   total de produtos: {total} ({total_pages} paginas)")
        if not batch:
            break
        products.extend(batch)
        if page >= total_pages:
            break
        page += 1
        time.sleep(DELAY)
    return products


def simplify(p: dict) -> dict:
    """Extrai os campos uteis do payload da API para o indice."""
    image = None
    categories = []
    try:
        media = p.get("_embedded", {}).get("wp:featuredmedia", [])
        if media:
            image = media[0].get("source_url")
    except Exception:
        pass
    try:
        for grp in p.get("_embedded", {}).get("wp:term", []):
            for t in grp:
                if t.get("taxonomy") == "categoria-de-produto":
                    categories.append(t.get("name"))
    except Exception:
        pass
    return {
        "id": p.get("id"),
        "slug": p.get("slug"),
        "title": (p.get("title") or {}).get("rendered", "").strip(),
        "link": p.get("link"),
        "image": image,
        "categories": categories,
        "modified": p.get("modified"),
    }


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"Base: {BASE_URL}\n")

    raw = enumerate_products()
    index = [simplify(p) for p in raw]

    (DATA / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[ok] indice salvo: data/index.json ({len(index)} produtos)")

    # Baixa/cacheia o HTML de cada pagina de produto
    print("\nBaixando paginas de produto (cache em data/raw/) ...")
    n_ok = n_skip = 0
    for i, prod in enumerate(index, 1):
        slug = prod["slug"]
        out = RAW / f"{slug}.html"
        if out.exists() and out.stat().st_size > 1000:
            n_skip += 1
            continue
        try:
            html, _ = http_get(prod["link"])
            out.write_text(html, encoding="utf-8")
            n_ok += 1
            print(f"  [{i}/{len(index)}] {slug} ({len(html)//1024}kb)")
            time.sleep(DELAY)
        except Exception as e:
            print(f"  [{i}/{len(index)}] ERRO {slug}: {e}", file=sys.stderr)
    print(f"\n[ok] paginas baixadas: {n_ok}, em cache: {n_skip}")
    print("Fase 1 concluida. Proximo: scraper/extract.py")


if __name__ == "__main__":
    main()
