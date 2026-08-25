#!/usr/bin/env python3
"""
Fase 2 do scraper: extrai dados estruturados (variantes/SKUs) das paginas
HTML cacheadas em data/raw/, cruzando com data/index.json.

Estrategia HIBRIDA:
  - Parser heuristico (deterministico, gratis) para o padrao regular:
        [Material] -> linhas de SKU -> Descricao:
  - Paginas que o heuristico nao consegue parsear com confianca sao
    listadas em data/needs_llm.json para o passo de fallback via LLM
    (scraper/extract_llm.py).

Saida: data/products.json  (catalogo estruturado completo)
Zero dependencias externas.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"

# Marcadores que delimitam / poluem a regiao de conteudo do produto
END_MARKERS = ("Solicitar orçamento", "Solicitar orcamento", "VOLTAR",
               "Segunda-feira a Quinta", "COPYRIGHT")
NAV_NOISE = {
    "Ir para o conteúdo", "Home", "Empresa", "Produtos", "Projetos",
    "Detalhes Técnicos", "Detalhes em Cad", "Notícias", "Vídeos", "Contato",
    "Search", "Carregar mais", "VOLTAR",
}
HERO_NOISE = (
    "Com nossos produtos", "Na Paratec, oferecemos",
)

# Codigo de SKU: PRT-101, PRT780, SG2, SG2-SG2C, PRT 282, etc.
# comeca com 2+ letras maiusculas, seguido de digitos/hifens (com espaco opcional).
CODE = r"[A-Z]{2,}[\s-]?\d[A-Z0-9]*(?:[-/][A-Z0-9]+)*"
# linha "CODIGO – resto"  (com travessao)
SKU_LINE_RE = re.compile(rf"^({CODE})\s*[–\-]\s*(.+)$")
# linha "CODIGO resto"  (sem travessao; exige digito no codigo p/ evitar falso-positivo)
SKU_NODASH_RE = re.compile(rf"^({CODE})\s+(.+)$")
CODE_ONLY_RE = re.compile(rf"^({CODE})$")
# codigo dentro do titulo (inicio, apos travessao ou apos espaco)
TITLE_CODE_RE = re.compile(rf"\b({CODE})\b")
DIM_RE = re.compile(r"(\d+[.,]?\d*\s?(?:mm|cm|m|\"|”|pol|polegadas|kg|g|mm²|mm2|awg)\b|\d+/\d+\")", re.I)


def normalize_sku(code: str) -> str:
    """Normaliza 'PRT 282' / 'PRT282' -> 'PRT-282'; mantem SG2-SG2C etc."""
    c = re.sub(r"\s+", " ", code.strip().upper())
    # espaco entre prefixo de letras e digitos -> hifen: 'PRT 282' -> 'PRT-282'
    c = re.sub(r"([A-Z])\s+(\d)", r"\1-\2", c)
    # normaliza espacos ao redor de hifens existentes
    c = re.sub(r"\s*-\s*", "-", c)
    return c


def sku_from_title(title: str):
    """Extrai o codigo do SKU embutido no titulo, se houver."""
    m = TITLE_CODE_RE.search(title)
    return normalize_sku(m.group(1)) if m else None


def clean_html_to_lines(raw: str):
    """Converte HTML em linhas de texto, marcando <strong>/<b> com sentinela."""
    h = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    # marca negrito (usado para nome do material)
    h = re.sub(r"<(strong|b)\b[^>]*>", "\x01", h)
    h = re.sub(r"</(strong|b)>", "\x02", h)
    # quebra por blocos e itens de lista
    h = re.sub(r"<li\b[^>]*>", "\n", h)
    h = re.sub(r"<(p|h[1-6]|div|br|tr|section)\b[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    lines = []
    for ln in h.split("\n"):
        strong = "\x01" in ln
        t = ln.replace("\x01", "").replace("\x02", "")
        t = re.sub(r"[ \t ]+", " ", t).strip()
        if t:
            lines.append((t, strong))
    return lines


def slice_content(lines, title: str):
    """Isola as linhas entre o titulo do produto e o rodape."""
    texts = [t for t, _ in lines]
    # fim: primeiro marcador de rodape
    end = len(lines)
    for i, t in enumerate(texts):
        if any(m in t for m in END_MARKERS):
            end = i
            break
    # inicio: ultima ocorrencia do titulo antes do fim
    norm_title = title.strip()
    start = None
    for i in range(min(end, len(lines)) - 1, -1, -1):
        if texts[i] == norm_title or texts[i].rstrip(" -–") == norm_title:
            start = i + 1
            break
    if start is None:
        # fallback: primeira linha apos o hero
        start = 0
        for i, t in enumerate(texts[:end]):
            if any(t.startswith(h) for h in HERO_NOISE):
                start = i + 1
    content = [
        (t, s) for t, s in lines[start:end]
        if t not in NAV_NOISE and not any(t.startswith(h) for h in HERO_NOISE)
    ]
    # Fallback: se ficou vazio, pega tudo apos o ultimo ruido de nav/hero ate o fim.
    if not content:
        last_noise = 0
        for i, t in enumerate(texts[:end]):
            if t in NAV_NOISE or any(t.startswith(h) for h in HERO_NOISE) or t == norm_title:
                last_noise = i + 1
        content = [
            (t, s) for t, s in lines[last_noise:end]
            if t not in NAV_NOISE and not any(t.startswith(h) for h in HERO_NOISE)
            and t != norm_title
        ]
    return content


def parse_variants(content):
    """
    Percorre as linhas do conteudo e monta as variantes.
    Retorna (variants, description_familia, confidence, leftover_lines).
    """
    variants = []
    family_desc_parts = []
    current_material = None
    pending = []  # variantes aguardando a 'Descricao:' do grupo
    leftover = []

    def flush_desc(desc):
        for v in pending:
            v["description"] = desc
        pending.clear()

    for t, strong in content:
        low = t.lower()
        if low.startswith("descrição") or low.startswith("descricao"):
            desc = re.sub(r"^descri[çc][ãa]o\s*:?\s*", "", t, flags=re.I).strip()
            if pending:
                flush_desc(desc)
            else:
                family_desc_parts.append(desc)
            continue

        def add_variant(code, rest):
            rest = (rest or "").strip()
            dim = None
            dm = DIM_RE.search(rest)
            if dm:
                dim = dm.group(1).strip()
            attributes = DIM_RE.sub("", rest).strip(" -–,") if dim else rest
            v = {
                "sku": normalize_sku(code),
                "material": current_material,
                "dimensions": dim,
                "attributes": attributes or None,
                "description": None,
                "raw_text": t,
            }
            variants.append(v)
            pending.append(v)

        m = SKU_LINE_RE.match(t)
        if m:
            add_variant(m.group(1), m.group(2))
            continue

        # linha em negrito curta e sem digitos => provavelmente nome de material
        if strong and len(t) <= 40 and not any(c.isdigit() for c in t):
            flush_desc(None)  # fecha grupo anterior sem descricao
            current_material = t.strip(" :")
            continue

        # linha "CODIGO resto" sem travessao (ex: 'SG2 Sequencial 2 Modulos')
        mn = SKU_NODASH_RE.match(t)
        if mn:
            add_variant(mn.group(1), mn.group(2))
            continue

        # linha isolada que parece so um codigo (sem dimensao) -> variante simples
        if CODE_ONLY_RE.match(t):
            v = {"sku": t, "material": current_material, "dimensions": None,
                 "attributes": None, "description": None, "raw_text": t}
            variants.append(v)
            pending.append(v)
            continue

        # sobra: texto que pode ser descricao geral da familia
        if len(t) > 15:
            family_desc_parts.append(t)
        else:
            leftover.append(t)

    # confianca: achou pelo menos 1 variante com SKU plausivel
    has_sku = any(re.search(r"\d", v["sku"] or "") for v in variants)
    confidence = "high" if variants and has_sku else ("low" if variants else "none")
    family_desc = " ".join(dict.fromkeys(family_desc_parts)).strip() or None
    return variants, family_desc, confidence, leftover


def main():
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    products = []
    needs_llm = []
    stats = {"high": 0, "low": 0, "none": 0, "missing_html": 0, "total_variants": 0}

    for prod in index:
        slug = prod["slug"]
        title = html.unescape(prod["title"])
        page = RAW / f"{slug}.html"
        if not page.exists():
            stats["missing_html"] += 1
            needs_llm.append({"slug": slug, "reason": "html ausente"})
            continue

        lines = clean_html_to_lines(page.read_text(encoding="utf-8"))
        content = slice_content(lines, title)
        variants, family_desc, confidence, leftover = parse_variants(content)
        raw_text = "\n".join(t for t, _ in content)

        # Fallback: SKU embutido no titulo (produto de variante unica).
        # Ex: "PRT780 - Conector...", "Suporte Telha - PRT 282".
        if not variants:
            tsku = sku_from_title(title)
            if tsku:
                variants = [{
                    "sku": tsku, "material": None, "dimensions": None,
                    "attributes": None,
                    "description": family_desc or (raw_text or None),
                    "raw_text": raw_text or title,
                }]
                confidence = "high"
                if family_desc is None and raw_text:
                    family_desc = raw_text

        stats[confidence if confidence in stats else "none"] += 1
        stats["total_variants"] += len(variants)

        for v in variants:
            v["extracted_by"] = "heuristic"

        products.append({
            "id": prod["id"],
            "slug": slug,
            "title": title,
            "categories": [c for c in prod["categories"] if c != "Produtos em Destaque"],
            "featured": "Produtos em Destaque" in prod["categories"],
            "image_url": prod["image"],
            "source_url": prod["link"],
            "wp_modified": prod.get("modified"),
            "description": family_desc,
            "variants": variants,
            "raw_text": raw_text,
            "confidence": confidence,
        })

        if confidence != "high":
            needs_llm.append({
                "slug": slug, "title": title, "reason": f"confianca={confidence}",
                "raw_text": raw_text,
            })

    (DATA / "products.json").write_text(
        json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "needs_llm.json").write_text(
        json.dumps(needs_llm, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Extracao heuristica concluida ===")
    print(f"  produtos:            {len(products)}")
    print(f"  variantes (SKUs):    {stats['total_variants']}")
    print(f"  confianca alta:      {stats['high']}")
    print(f"  confianca baixa:     {stats['low']}")
    print(f"  sem variantes:       {stats['none']}")
    print(f"  html ausente:        {stats['missing_html']}")
    print(f"  -> precisam de LLM:  {len(needs_llm)}  (data/needs_llm.json)")
    print(f"\n[ok] data/products.json")


if __name__ == "__main__":
    main()
