"use client";

import { Badge, Card, EmptyState, Pill } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import type { Categoria, Produto } from "@/lib/types";
import { cn } from "@/lib/cn";
import {
  Boxes,
  ExternalLink,
  Layers,
  Package,
  Search,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

export default function CatalogoPage() {
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [sel, setSel] = useState<Produto | null>(null);

  // Categorias uma vez.
  useEffect(() => {
    api.categorias().then(setCategorias).catch(() => setCategorias([]));
  }, []);

  // Produtos reagem a busca/categoria (com debounce simples).
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api
        .produtos({ q: q || undefined, categoria: cat || undefined })
        .then((p) => {
          setProdutos(p);
          setOffline(false);
        })
        .catch(() => {
          setProdutos([]);
          setOffline(true);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q, cat]);

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      {/* Busca + categorias */}
      <div className="flex flex-col gap-3">
        <div className="relative max-w-md">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por nome, SKU ou material…"
            className="w-full rounded-lg border bg-surface py-2.5 pl-9 pr-3 text-sm text-ink outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/40"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setCat(null)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition",
              !cat
                ? "bg-feature text-feature-fg"
                : "bg-surface text-muted ring-1 ring-inset ring-border hover:text-ink",
            )}
          >
            Todas
          </button>
          {categorias.map((c) => (
            <button
              key={c.name}
              onClick={() => setCat(c.name === cat ? null : c.name)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition",
                cat === c.name
                  ? "bg-feature text-feature-fg"
                  : "bg-surface text-muted ring-1 ring-inset ring-border hover:text-ink",
              )}
            >
              {c.name}
              <span className="ml-1.5 text-faint">{c.n_produtos}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Grade */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-28 animate-pulse rounded-2xl border bg-surface-2"
            />
          ))}
        </div>
      ) : produtos.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Package size={28} />}
            title="Nenhum produto encontrado"
            hint="Ajuste a busca ou o filtro de categoria."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {produtos.map((p) => (
            <button
              key={p.id}
              onClick={() => setSel(p)}
              className="group flex flex-col rounded-2xl border bg-surface p-4 text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-lift"
            >
              <div className="flex items-start justify-between">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                  <Package size={18} />
                </span>
                {p.n_variantes ? (
                  <Badge tone="neutral">
                    <Layers size={11} /> {p.n_variantes} SKUs
                  </Badge>
                ) : null}
              </div>
              <p className="mt-3 line-clamp-2 text-sm font-semibold text-ink">
                {p.title}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {(p.categorias ?? []).slice(0, 2).map((c) => (
                  <span
                    key={c}
                    className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      )}

      {sel && <ProdutoDrawer slug={sel.slug} base={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

function ProdutoDrawer({
  slug,
  base,
  onClose,
}: {
  slug: string;
  base: Produto;
  onClose: () => void;
}) {
  const [prod, setProd] = useState<Produto | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    api
      .produto(slug)
      .then(setProd)
      .catch(() => setErro(true));
  }, [slug]);

  const p = prod ?? base;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <aside className="relative z-10 flex h-full w-full max-w-md flex-col bg-surface shadow-lift animate-fade-in">
        <div className="flex items-start justify-between border-b px-5 py-4">
          <div>
            <p className="text-xs text-muted">Produto</p>
            <h2 className="text-base font-semibold text-ink">{p.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <div className="flex flex-wrap gap-1.5">
            {(p.categorias ?? []).map((c) => (
              <Badge key={c} tone="accent">
                {c}
              </Badge>
            ))}
          </div>

          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              <Boxes size={13} /> Variantes / SKUs
            </p>
            {erro && !prod ? (
              <p className="text-xs text-muted">
                Não foi possível carregar as variantes (backend offline).
              </p>
            ) : p.variantes && p.variantes.length > 0 ? (
              <div className="space-y-2">
                {p.variantes.map((v) => (
                  <div
                    key={v.sku}
                    className="rounded-xl border bg-surface-2 p-3"
                  >
                    <div className="flex items-center justify-between">
                      <Pill>{v.sku}</Pill>
                      {v.material && (
                        <span className="text-[11px] text-muted">{v.material}</span>
                      )}
                    </div>
                    {v.dimensions && (
                      <p className="mt-1.5 text-xs text-ink">{v.dimensions}</p>
                    )}
                    {v.description && (
                      <p className="mt-1 text-xs text-muted">{v.description}</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">Carregando variantes…</p>
            )}
          </div>
        </div>

        {p.source_url && (
          <div className="border-t p-4">
            <a
              href={p.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-accent-ink hover:underline"
            >
              Ver página no site <ExternalLink size={12} />
            </a>
          </div>
        )}
      </aside>
    </div>
  );
}
