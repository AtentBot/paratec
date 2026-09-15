"use client";

import { Badge, Card, EmptyState, Pill } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import type { Categoria, Produto } from "@/lib/types";
import { cn } from "@/lib/cn";
import {
  Boxes,
  Download,
  ExternalLink,
  Layers,
  Loader2,
  Package,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

export default function CatalogoPage() {
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [sel, setSel] = useState<Produto | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [reload, setReload] = useState(0);

  // Categorias (recarrega após importar/limpar).
  useEffect(() => {
    api.categorias().then(setCategorias).catch(() => setCategorias([]));
  }, [reload]);

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
  }, [q, cat, reload]);

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      {/* Busca + categorias */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <div className="relative max-w-md flex-1">
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
          <button
            onClick={() => setImportOpen(true)}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-feature px-3.5 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90"
          >
            <Upload size={15} /> Importar catálogo
          </button>
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
      {importOpen && (
        <ImportarModal
          onClose={() => setImportOpen(false)}
          onDone={() => setReload((r) => r + 1)}
        />
      )}
    </div>
  );
}

function ImportarModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [res, setRes] = useState<{ produtos: number; variantes: number; categorias: number } | null>(null);

  async function importar() {
    if (!file) return;
    setBusy(true);
    setErro(null);
    setRes(null);
    try {
      const r = await api.importarCatalogo(file);
      setRes(r);
      onDone();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "falha ao importar");
    }
    setBusy(false);
  }

  async function limpar() {
    if (!confirm("Apagar TODO o catálogo desta conta? Esta ação não pode ser desfeita.")) return;
    setBusy(true);
    setErro(null);
    try {
      await api.limparCatalogo();
      setRes(null);
      onDone();
      onClose();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "falha ao limpar");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-2xl border bg-surface p-6 shadow-lift animate-fade-in">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">Importar catálogo</h2>
            <p className="mt-0.5 text-xs text-muted">
              Envie um CSV com seus produtos. Reimportar atualiza pelos nomes já existentes.
            </p>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>

        <div className="mt-5 flex flex-col gap-4">
          <a
            href={api.modeloCatalogoUrl()}
            className="inline-flex w-fit items-center gap-2 text-sm font-medium text-accent-ink hover:underline"
          >
            <Download size={14} /> Baixar modelo (CSV)
          </a>

          <div
            onClick={() => inputRef.current?.click()}
            className="cursor-pointer rounded-xl border border-dashed bg-surface-2 px-4 py-8 text-center transition hover:border-accent"
          >
            <Upload size={22} className="mx-auto text-faint" />
            <p className="mt-2 text-sm text-ink">
              {file ? file.name : "Clique para escolher o arquivo CSV"}
            </p>
            <p className="text-[11px] text-muted">Colunas: produto, categoria, sku, material, dimensoes, atributos, descricao</p>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>

          {res && (
            <div className="rounded-lg bg-success/10 px-3 py-2 text-sm text-success">
              Importado: {res.produtos} produtos, {res.variantes} variantes, {res.categorias} categorias.
            </div>
          )}
          {erro && <p className="text-sm text-danger">{erro}</p>}

          <div className="flex items-center justify-between gap-2">
            <button
              onClick={limpar}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-danger transition hover:bg-danger/10 disabled:opacity-50"
            >
              <Trash2 size={14} /> Limpar catálogo
            </button>
            <div className="flex gap-2">
              <button onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted transition hover:text-ink">
                Fechar
              </button>
              <button
                onClick={importar}
                disabled={!file || busy}
                className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50"
              >
                {busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                Importar
              </button>
            </div>
          </div>
        </div>
      </div>
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
