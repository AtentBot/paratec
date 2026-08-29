// Cliente do agent-service (FastAPI). Todas as seções agora consomem dados
// reais; não há mais fixtures. Falhas de rede são tratadas por `tryApi`.
import type {
  CatalogStats,
  Categoria,
  ConversaDetalhe,
  ConversaResumo,
  FilaItem,
  Metrics,
  Produto,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_AGENT_API?.replace(/\/$/, "") ||
  "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  base: BASE,

  // Catálogo
  stats: () => get<CatalogStats>("/catalog/stats"),
  categorias: () => get<Categoria[]>("/catalog/categorias"),
  produtos: (params: { q?: string; categoria?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.categoria) qs.set("categoria", params.categoria);
    qs.set("limit", String(params.limit ?? 60));
    return get<Produto[]>(`/catalog/produtos?${qs.toString()}`);
  },
  produto: (idOrSlug: string) =>
    get<Produto>(`/catalog/produtos/${encodeURIComponent(idOrSlug)}`),

  // Métricas
  metrics: () => get<Metrics>("/metrics/overview"),

  // Conversas
  conversas: (status?: string) =>
    get<ConversaResumo[]>(`/conversas${status ? `?status=${status}` : ""}`),
  conversa: (threadId: string) =>
    get<ConversaDetalhe>(`/conversas/${encodeURIComponent(threadId)}`),
  assumirConversa: (threadId: string) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/assumir`),

  // Fila humana
  fila: (params: { tipo?: string; status?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.tipo) qs.set("tipo", params.tipo);
    if (params.status) qs.set("status", params.status);
    const s = qs.toString();
    return get<FilaItem[]>(`/fila${s ? `?${s}` : ""}`);
  },
  atualizarFila: (id: number, body: { status?: string; responsavel?: string }) =>
    send<FilaItem>("PATCH", `/fila/${id}`, body),
};

/** Envolve uma chamada de API devolvendo `null` se o backend estiver fora. */
export async function tryApi<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch {
    return null;
  }
}
