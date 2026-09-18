// Cliente do agent-service (FastAPI). Todas as seções agora consomem dados
// reais; não há mais fixtures. Falhas de rede são tratadas por `tryApi`.
import type {
  AdminApiChave,
  AdminConsumoTenant,
  AdminOverview,
  AdminPlanos,
  AdminWhatsappVerificacao,
  AdminTenant,
  AdminTicketDetalhe,
  AdminTicketResumo,
  Agente,
  ApiChave,
  ApiChaveCriada,
  ApiEscopo,
  ApiLog,
  ApiResumo,
  AssinaturaStatus,
  Broadcast,
  Capacidade,
  CapacidadeInfo,
  CatalogStats,
  Categoria,
  Cliente,
  ConversaDetalhe,
  ConversaResumo,
  FilaItem,
  Me,
  Metrics,
  Plano,
  Uso,
  Produto,
  RagFonte,
  RagStatus,
  RelatorioResumo,
  TicketDetalhe,
  TicketResumo,
  Vendedor,
  Webhook,
  WebhookEntrega,
  WebhookEvento,
  WebhookResultado,
  WhatsappConfig,
  WhatsappInstancia,
  WhatsappQrCode,
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

function _qs(p: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  return q.toString();
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

/** Como `send`, mas propaga a mensagem `detail` do backend (validações). */
async function sendDetalhe<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const d = data?.detail;
    throw new Error(typeof d === "string" ? d : `${method} ${path} -> ${res.status}`);
  }
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

  // Importação self-serve do catálogo (CSV).
  modeloCatalogoUrl: () => `${BASE}/catalog/modelo.csv`,
  importarCatalogo: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/catalog/import`, {
      method: "POST", body: fd, cache: "no-store", credentials: "include",
    }).then(async (r) => {
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `erro ${r.status}`);
      return r.json() as Promise<{ produtos: number; variantes: number; categorias: number }>;
    });
  },
  limparCatalogo: () => send<{ removidos: number }>("DELETE", "/catalog"),

  // Clientes
  clientes: (status?: string) =>
    get<Cliente[]>(`/clientes${status ? `?status=${status}` : ""}`),
  cliente: (telefone: string) =>
    get<Cliente>(`/clientes/${encodeURIComponent(telefone)}`),

  // Usuário logado (sessão própria do agent-service). Cai em nulos se deslogado.
  whoami: () =>
    fetch(`${BASE}/auth/me`, { cache: "no-store", credentials: "include" })
      .then((r) => (r.ok ? r.json() : { username: null, name: null }))
      .catch(() => ({ username: null, name: null })),

  // --- Autenticação (sessão por cookie) ---
  me: () => get<Me>("/auth/me"),
  login: (email: string, senha: string) =>
    send<{ email: string; nome: string | null; role: string; tenant_id: number }>(
      "POST", "/auth/login", { email, senha },
    ),
  // Cadastro NÃO abre sessão: envia o link de confirmação por e-mail.
  signup: (body: {
    empresa: string; email: string; senha: string; whatsapp: string; nome?: string; plano?: string;
  }) =>
    send<{ verificacao_enviada: boolean; email: string }>("POST", "/auth/signup", body),
  verificarEmail: (token: string) =>
    send<{ email: string; nome: string | null; role: string; tenant_id: number }>(
      "POST", "/auth/verify-email", { token },
    ),
  reenviarVerificacao: (email: string, plano?: string) =>
    send<{ ok: boolean }>("POST", "/auth/resend-verification", { email, plano }),
  // Verificação do WhatsApp (código de 6 dígitos). Erros trazem o `detail`.
  whatsappEnviarCodigo: (telefone?: string) =>
    sendDetalhe<{ enviado: boolean; whatsapp: string; expira_em_min: number }>(
      "POST", "/auth/whatsapp/send-code", telefone ? { telefone } : {},
    ),
  whatsappVerificar: (codigo: string) =>
    sendDetalhe<{ verificado: boolean; whatsapp: string }>("POST", "/auth/whatsapp/verify", { codigo }),
  logout: () => send<{ ok: boolean }>("POST", "/auth/logout"),
  trocarSenha: (senha_atual: string, senha_nova: string) =>
    send<{ ok: boolean }>("POST", "/auth/change-password", { senha_atual, senha_nova }),

  // --- Billing (Stripe) ---
  planos: () => get<Plano[]>("/billing/plans"),
  assinaturaStatus: () => get<AssinaturaStatus>("/billing/status"),
  uso: () => get<Uso>("/billing/usage"),
  checkout: (plano: string) =>
    send<{ url: string }>("POST", "/billing/checkout", { plano }),
  comprarPacote: (pacote: string) =>
    send<{ url: string }>("POST", "/billing/pacotes/checkout", { pacote }),
  cancelarAssinatura: (pesquisa?: { respostas?: Record<string, string>; comentario?: string }) =>
    send<AssinaturaStatus>("POST", "/billing/cancel", pesquisa ?? {}),
  reativarAssinatura: () => send<AssinaturaStatus>("POST", "/billing/reactivate"),

  // --- Suporte / Chamados ---
  suporteEmail: () => get<{ email: string }>("/suporte/config"),
  chamados: (status?: string) =>
    get<TicketResumo[]>(`/suporte/chamados${status ? `?status=${status}` : ""}`),
  chamado: (id: number) => get<TicketDetalhe>(`/suporte/chamados/${id}`),
  abrirChamado: (body: {
    assunto: string; descricao: string; categoria?: string; prioridade?: string;
  }) => send<TicketResumo>("POST", "/suporte/chamados", body),
  responderChamado: (id: number, corpo: string) =>
    send<TicketDetalhe>("POST", `/suporte/chamados/${id}/mensagens`, { corpo }),
  statusChamado: (id: number, status: string) =>
    send<TicketDetalhe>("PATCH", `/suporte/chamados/${id}`, { status }),

  // --- Central admin (staff/Dew) ---
  adminOverview: () => get<AdminOverview>("/admin/overview"),
  adminTenants: (p: { q?: string; limit?: number; offset?: number } = {}) =>
    get<{ items: AdminTenant[]; total: number }>(`/admin/tenants?${_qs(p)}`),
  adminSetAssinatura: (tenantId: number, body: { status: string; plan?: string }) =>
    send<AssinaturaStatus>("PATCH", `/admin/tenants/${tenantId}/assinatura`, body),
  // WhatsApp da plataforma (envia os códigos de verificação do cadastro).
  adminWaVerificacao: () => get<AdminWhatsappVerificacao>("/admin/whatsapp-verificacao"),
  adminWaVerificacaoSincronizar: (nome: string) =>
    sendDetalhe<{ nome: string; qrcode: WhatsappQrCode }>("POST", "/admin/whatsapp-verificacao", { nome }),
  adminWaVerificacaoQrcode: () =>
    get<{ nome: string; qrcode: WhatsappQrCode }>("/admin/whatsapp-verificacao/qrcode"),
  adminWaVerificacaoStatus: () => get<WhatsappInstancia>("/admin/whatsapp-verificacao/status"),
  adminWaVerificacaoTeste: (telefone: string) =>
    sendDetalhe<{ enviado: boolean; whatsapp: string }>("POST", "/admin/whatsapp-verificacao/teste", { telefone }),
  adminWaVerificacaoDesconectar: () =>
    sendDetalhe<{ estado: string }>("POST", "/admin/whatsapp-verificacao/desconectar"),
  adminWaVerificacaoRemover: () =>
    sendDetalhe<{ removido: string }>("DELETE", "/admin/whatsapp-verificacao"),
  adminPlanos: () => get<AdminPlanos>("/admin/planos"),
  adminAlterarPreco: (plano: string, body: { preco: number; aplicar_existentes: boolean }) =>
    send<AdminPlanos>("PATCH", `/admin/planos/${plano}`, body),
  adminAlterarCota: (plano: string, mensagens_incluidas: number) =>
    send<AdminPlanos>("PATCH", `/admin/planos/${plano}/cota`, { mensagens_incluidas }),
  adminAlterarPacote: (pacote: string, body: { mensagens?: number; preco?: number; ativo?: boolean }) =>
    send<AdminPlanos>("PATCH", `/admin/pacotes/${pacote}`, body),
  adminConsumo: (p: { q?: string; limit?: number; offset?: number } = {}) =>
    get<{ items: AdminConsumoTenant[]; totais: { tenants: number; tokens: number; custo: number } }>(
      `/admin/consumo?${_qs(p)}`,
    ),
  adminChamados: (p: { status?: string; prioridade?: string; q?: string; limit?: number; offset?: number } = {}) =>
    get<{ items: AdminTicketResumo[]; total: number }>(`/admin/chamados?${_qs(p)}`),
  adminChamado: (id: number) => get<AdminTicketDetalhe>(`/admin/chamados/${id}`),
  adminResponderChamado: (id: number, corpo: string) =>
    send<AdminTicketDetalhe>("POST", `/admin/chamados/${id}/mensagens`, { corpo }),
  adminAtualizarChamado: (id: number, body: { status?: string; prioridade?: string }) =>
    send<AdminTicketDetalhe>("PATCH", `/admin/chamados/${id}`, body),

  // --- Integrações (API pública por tenant) ---
  apiEscopos: () => get<{ escopos: ApiEscopo[]; max_chaves: number }>("/integracoes/escopos"),
  apiResumo: () => get<ApiResumo>("/integracoes/resumo"),
  apiChaves: () => get<ApiChave[]>("/integracoes/chaves"),
  apiCriarChave: (body: {
    nome: string;
    escopos: string[];
    ips_permitidos: string[];
    rate_limit_min: number;
    expira_em_dias: number | null;
  }) => sendDetalhe<ApiChaveCriada>("POST", "/integracoes/chaves", body),
  apiAtualizarChave: (
    id: number,
    body: { nome?: string; escopos?: string[]; ips_permitidos?: string[]; rate_limit_min?: number },
  ) => sendDetalhe<ApiChave>("PATCH", `/integracoes/chaves/${id}`, body),
  apiRotacionarChave: (id: number) =>
    sendDetalhe<ApiChaveCriada>("POST", `/integracoes/chaves/${id}/rotacionar`),
  apiRevogarChave: (id: number) => sendDetalhe<ApiChave>("DELETE", `/integracoes/chaves/${id}`),
  apiLogs: (p: { chave_id?: number; limit?: number; offset?: number } = {}) =>
    get<{ items: ApiLog[]; total: number }>(`/integracoes/logs?${_qs(p)}`),
  webhookEventos: () =>
    get<{ eventos: WebhookEvento[]; max_webhooks: number }>("/integracoes/webhooks/eventos"),
  webhooks: () => get<Webhook[]>("/integracoes/webhooks"),
  criarWebhook: (body: { url: string; descricao?: string; eventos: string[] }) =>
    sendDetalhe<Webhook & { segredo: string }>("POST", "/integracoes/webhooks", body),
  atualizarWebhook: (id: number, body: { url?: string; descricao?: string; eventos?: string[]; ativo?: boolean }) =>
    sendDetalhe<Webhook>("PATCH", `/integracoes/webhooks/${id}`, body),
  removerWebhook: (id: number) => sendDetalhe<{ removido: number }>("DELETE", `/integracoes/webhooks/${id}`),
  revelarSegredoWebhook: (id: number) => sendDetalhe<{ segredo: string }>("GET", `/integracoes/webhooks/${id}/segredo`),
  rotacionarSegredoWebhook: (id: number) =>
    sendDetalhe<{ segredo: string }>("POST", `/integracoes/webhooks/${id}/rotacionar-segredo`),
  testarWebhook: (id: number) => sendDetalhe<WebhookResultado>("POST", `/integracoes/webhooks/${id}/testar`),
  entregasWebhook: (p: { webhook_id?: number; limit?: number; offset?: number } = {}) =>
    get<{ items: WebhookEntrega[]; total: number }>(`/integracoes/webhooks/entregas?${_qs(p)}`),
  reenviarEntrega: (id: number) =>
    sendDetalhe<WebhookResultado>("POST", `/integracoes/webhooks/entregas/${id}/reenviar`),
  adminApiChaves: (p: { q?: string; limit?: number; offset?: number } = {}) =>
    get<{ items: AdminApiChave[]; total: number }>(`/admin/integracoes?${_qs(p)}`),
  adminRevogarApiChave: (id: number) =>
    sendDetalhe<ApiChave>("POST", `/admin/integracoes/${id}/revogar`),

  // Relatórios (por período)
  relatorioResumo: (desde: string, ate: string) =>
    get<RelatorioResumo>(`/relatorios/resumo?desde=${desde}&ate=${ate}`),
  relatorioConversasCsvUrl: (desde: string, ate: string) =>
    `${BASE}/relatorios/conversas.csv?desde=${desde}&ate=${ate}`,

  // Base de conhecimento (RAG)
  ragStatus: () => get<RagStatus>("/rag/status"),
  ragFontes: () => get<RagFonte[]>("/rag/fontes"),
  ragReindexarCatalogo: () => send<{ ingeridos: number }>("POST", "/rag/ingest"),
  ragRemoverFonte: (source: string) =>
    send<{ removidos: number }>("DELETE", `/rag/fontes/${encodeURIComponent(source)}`),
  ragUpload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/rag/upload`, { method: "POST", body: fd, cache: "no-store" }).then(
      async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json() as Promise<{ fonte: string; chunks: number }>;
      },
    );
  },

  // Métricas
  metrics: () => get<Metrics>("/metrics/overview"),
  // Total de não-lidas (badge global do menu Atendimento).
  unreadTotal: () => get<{ total: number }>("/metrics/unread"),

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
  // Zera o contador de não-lidas ao abrir a conversa.
  marcarLida: (threadId: string) =>
    send<ConversaDetalhe>("POST", `/conversas/${encodeURIComponent(threadId)}/ler`),
  // URL do stream SSE (push em tempo real) desta conversa.
  streamUrl: (threadId: string) =>
    `${BASE}/conversas/${encodeURIComponent(threadId)}/stream`,

  // Orçamentos (comercial) = fila de pedidos
  orcamentos: (status?: string) =>
    get<FilaItem[]>(`/orcamentos${status ? `?status=${status}` : ""}`),

  // Broadcast / promoções
  broadcasts: () => get<Broadcast[]>("/broadcasts"),
  broadcastSegmentos: () => get<Record<string, number>>("/broadcast/segmentos"),
  // Envia uma promoção. Passe `telefones` (seleção manual) OU `segmento`.
  // `imagem` = caminho devolvido por `uploadPromocaoImagem` (banner opcional).
  enviarBroadcast: (payload: {
    texto: string;
    segmento?: string;
    telefones?: string[];
    imagem?: string | null;
    criado_por?: string;
  }) =>
    send<{ id: number; total: number; status: string }>("POST", "/broadcast", payload),
  // Sobe a imagem do banner; devolve o caminho para usar em `enviarBroadcast`.
  uploadPromocaoImagem: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/broadcast/upload`, { method: "POST", body: fd, cache: "no-store" }).then(
      async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json() as Promise<{ arquivo: string; url: string; mimetype: string }>;
      },
    );
  },
  // URL absoluta (via proxy /agent) de um arquivo em /media.
  mediaUrl: (path: string) => `${BASE}${path.startsWith("/") ? path : `/${path}`}`,
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

  // Equipe de vendas (vendedores)
  vendedores: (ativo?: boolean) =>
    get<Vendedor[]>(`/vendedores${ativo ? "?ativo=true" : ""}`),
  criarVendedor: (body: {
    nome: string;
    telefone: string;
    email?: string | null;
    ativo?: boolean;
  }) => send<Vendedor>("POST", "/vendedores", body),
  atualizarVendedor: (
    id: number,
    body: { nome?: string; telefone?: string; email?: string | null; ativo?: boolean },
  ) => send<Vendedor>("PATCH", `/vendedores/${id}`, body),
  removerVendedor: (id: number) =>
    send<{ removido: number }>("DELETE", `/vendedores/${id}`),

  // WhatsApp — conexões (Configurações). O agent-service é proxy da Evolution:
  // o painel nunca recebe a URL/chave da Evolution.
  whatsappConfig: () => get<WhatsappConfig>("/whatsapp/config"),
  whatsappInstancias: () => get<WhatsappInstancia[]>("/whatsapp/instancias"),
  whatsappCriar: (nome: string) =>
    send<{ nome: string; qrcode: WhatsappQrCode }>("POST", "/whatsapp/instancias", { nome }),
  whatsappQrcode: (nome: string) =>
    get<{ nome: string; qrcode: WhatsappQrCode }>(
      `/whatsapp/instancias/${encodeURIComponent(nome)}/qrcode`,
    ),
  whatsappStatus: (nome: string) =>
    get<WhatsappInstancia>(`/whatsapp/instancias/${encodeURIComponent(nome)}/status`),
  whatsappDesconectar: (nome: string) =>
    send<{ nome: string; estado: string }>(
      "POST",
      `/whatsapp/instancias/${encodeURIComponent(nome)}/desconectar`,
    ),
  whatsappRemover: (nome: string) =>
    send<{ removido: string }>("DELETE", `/whatsapp/instancias/${encodeURIComponent(nome)}`),

  // Agentes (multi-agente por número de WhatsApp)
  agentes: () => get<Agente[]>("/agentes"),
  agenteCapacidades: () => get<CapacidadeInfo[]>("/agentes/capacidades"),
  criarAgente: (body: {
    nome: string;
    descricao?: string | null;
    instancia?: string | null;
    persona?: string | null;
    capacidades?: Capacidade[];
    ativo?: boolean;
    hiperpersonalizacao?: boolean;
  }) => send<Agente>("POST", "/agentes", body),
  atualizarAgente: (
    id: number,
    body: {
      nome?: string;
      descricao?: string | null;
      instancia?: string | null;
      persona?: string | null;
      capacidades?: Capacidade[];
      ativo?: boolean;
      hiperpersonalizacao?: boolean;
    },
  ) => send<Agente>("PATCH", `/agentes/${id}`, body),
  removerAgente: (id: number) => send<{ removido: number }>("DELETE", `/agentes/${id}`),

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
