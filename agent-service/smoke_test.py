"""Smoke test do serviço: valida a camada de catálogo contra o Postgres real
e verifica que o app FastAPI + o grafo importam. Não chama o LLM (não requer
GOOGLE_API_KEY)."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app import catalog  # noqa: E402

print("== listar_categorias ==")
cats = catalog.listar_categorias()
print(f"  {len(cats)} categorias; ex:", cats[0] if cats else None)

print("== buscar_produtos('captor') ==")
res = catalog.buscar_produtos("captor")
print(f"  {len(res)} produtos")
for p in res[:2]:
    print("   -", p["title"], "->", [v["sku"] for v in p["variantes"]])

print("== buscar_por_sku('PRT101') ==")
print("  ", catalog.buscar_por_sku("PRT101"))

print("== detalhes_produto (slug) ==")
d = catalog.detalhes_produto("captor-franklin-1-descida")
print("  ", d["title"], "| categorias:", d["categorias"], "| variantes:", len(d["variantes"]))

print("== import do app FastAPI + grafo ==")
from app import main, agents  # noqa: E402,F401
print("  app:", main.app.title, "| rotas:", [r.path for r in main.app.routes if hasattr(r, "path")])

print("== compilação da malha multi-agente ==")
os.environ.setdefault("GOOGLE_API_KEY", "dummy-compile-only")
g = agents.get_app().get_graph()
print("  nós:", [n for n in g.nodes])

print("\nOK — camada de dados, app e malha de agentes validados.")
