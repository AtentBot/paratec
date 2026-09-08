// Cliente do agent-service (FastAPI). Todas as seções agora consomem dados
// reais; não há mais fixtures. Falhas de rede são tratadas por `tryApi`.
import type {
  Broadcast,
  CatalogStats,
  Categoria,
  Cliente,
  ConversaDetalhe,
  ConversaResumo,
  FilaItem,
  Metrics,
  Produto,
  RelatorioResumo,
} from "./types";

// No NAVEGADOR: same-origin "/agent" (o Next faz proxy p/ o agent-service
// interno — ver next.config.mjs). No SERVIDOR (SSR): URL interna absoluta,
// pois fetch relativo não funciona no server. Dev local: defina
// NEXT_PUBLIC_AGENT_API=http://localhost:8000 (vale nos dois lados).
const isServer = typeof window === "undefined";
const BASE =
  process.env.NEXT_PUBLIC_AGENT_API?.replace(/\/$/, "") ||
  (isServer
    ? process.env.AGENT_INTERNAL_URL || "http://paratec-agent:8000"
    : "/agent");

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

  // Clientes
  clientes: (status?: string) =>
    get<Cliente[]>(`/clientes${status ? `?status=${status}` : ""}`),
  cliente: (telefone: string) =>
    get<Cliente>(`/clientes/${encodeURIComponent(telefone)}`),

  // Usuário logado (via Authentik forward-auth headers) — rota Next same-origin
  whoami: () =>
    fetch("/whoami", { cache: "no-store" })
      .then((r) => r.json() as Promise<{ username: string | null; name: string | null }>)
      .catch(() => ({ username: null, name: null })),

  // Relatórios (por período)
  relatorioResumo: (desde: string, ate: string) =>
    get<RelatorioResumo>(`/relatorios/resumo?desde=${desde}&ate=${ate}`),
  relatorioConversasCsvUrl: (desde: string, ate: string) =>
    `${BASE}/relatorios/conversas.csv?desde=${desde}&ate=${ate}`,

  // Métricas
  metrics: () => get<Metrics>("/metrics/overview"),

  // Conversas / Atendimento
  conversas: (params: { status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.q) qs.set("q", params.q);
    const s = qs.toString();
    return get<ConversaResumo[]>(`/conversas${s ? `?${s}` : ""}`);
  },
  conversa: (threadId: string) =>
    get<ConversaDetalhe>(`/conversas/${encodeURIComponent(threadId)}`),
  addNota: (threadId: string, texto: string, autor?: string) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/nota`, {
      texto,
      autor,
    }),
  atribuir: (threadId: string, responsavel: string | null) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/atribuir`, {
      responsavel,
    }),
  assumirConversa: (threadId: string) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/assumir`),
  // Liga/desliga a resposta automática da IA nesta conversa.
  setBot: (threadId: string, ativo: boolean) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/bot`, {
      ativo,
    }),
  resolverConversa: (threadId: string) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/resolver`),
  reabrirConversa: (threadId: string) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/reabrir`),

  // Orçamentos (comercial) = fila de pedidos
  orcamentos: (status?: string) =>
    get<FilaItem[]>(`/orcamentos${status ? `?status=${status}` : ""}`),

  // Broadcast / promoções
  broadcasts: () => get<Broadcast[]>("/broadcasts"),
  broadcastSegmentos: () => get<Record<string, number>>("/broadcast/segmentos"),
  enviarBroadcast: (texto: string, segmento = "todos", criado_por?: string) =>
    send<{ id: number; total: number; status: string }>("POST", "/broadcast", {
      texto,
      segmento,
      criado_por,
    }),
  responderConversa: (threadId: string, texto: string) =>
    send<ConversaDetalhe>(
      "POST",
      `/conversas/${encodeURIComponent(threadId)}/responder`,
      { texto },
    ),

  // URLs de exportação (download direto pelo navegador)
  clientesCsvUrl: (status?: string) =>
    `${BASE}/clientes.csv${status ? `?status=${status}` : ""}`,
  filaCsvUrl: (params: { tipo?: string; status?: string } = {}) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return `${BASE}/fila.csv${qs ? `?${qs}` : ""}`;
  },

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
