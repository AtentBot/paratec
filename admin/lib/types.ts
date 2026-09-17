// Tipos do domínio Paratec — espelham as respostas do agent-service (FastAPI).

export type Especialista = "produtos" | "pedidos" | "entrega" | "boletos";
export type ConversaStatus = "ia" | "humano" | "resolvida";

// --- Catálogo -------------------------------------------------------------

export interface Variante {
  sku: string;
  material: string | null;
  dimensions: string | null;
  description: string | null;
  attributes?: Record<string, unknown> | string | null;
}

export interface Produto {
  id: number;
  title: string;
  slug: string;
  source_url: string | null;
  n_variantes?: number;
  categorias?: string[];
  variantes?: Variante[];
}

export interface Categoria {
  name: string;
  n_produtos: number;
}

export interface CatalogStats {
  produtos: number;
  variantes: number;
  categorias: number;
}

// --- Clientes -------------------------------------------------------------

export type ClienteStatus = "pendente" | "ativo";

export interface Cliente {
  telefone: string;
  razao_social: string | null;
  cnpj: string | null;
  email: string | null;
  nome_contato: string | null;
  status: ClienteStatus;
  opt_out?: boolean;
  created_at: string;
  updated_at: string;
}

// --- Equipe de vendas -----------------------------------------------------

export interface Vendedor {
  id: number;
  nome: string;
  telefone: string;
  email: string | null;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

// --- WhatsApp (conexões / Configurações) ----------------------------------

export type WhatsappEstado = "conectado" | "conectando" | "desconectado";

export interface WhatsappInstancia {
  nome: string;
  estado: WhatsappEstado;
  numero: string | null;
  perfil: string | null;
}

export interface WhatsappQrCode {
  base64: string | null; // data:image/png;base64,... (pronto para <img src>)
  code: string | null;
  pairing_code: string | null;
}

export interface WhatsappConfig {
  configurado: boolean;
  webhook_automatico: boolean;
  instancia_padrao: string;
}

// --- Agentes (multi-agente por número) ------------------------------------

export type Capacidade = "catalogo" | "pedidos" | "entrega" | "boletos" | "conhecimento";

export interface CapacidadeInfo {
  chave: Capacidade;
  label: string;
}

export interface Agente {
  id: number;
  nome: string;
  descricao: string | null;
  instancia: string | null; // conexão de WhatsApp (número) amarrada
  persona: string | null;
  capacidades: Capacidade[];
  ativo: boolean;
  is_default: boolean; // agente catch-all (atende números sem agente próprio)
  hiperpersonalizacao: boolean; // usa histórico do cliente como contexto
  created_at: string;
  updated_at: string;
}

export interface RagStatus {
  enabled: boolean;
  chunks?: number;
  fontes?: number;
  erro?: string;
}

export interface RagFonte {
  source: string;
  chunks: number;
  atualizado: string;
}

export interface RelatorioResumo {
  atendimentos: number;
  resolvidas: number;
  handoffs: number;
  novos_clientes: number;
  orcamentos: number;
  campanhas: number;
  opt_outs: number;
}

export type BroadcastStatus = "enviando" | "concluido" | "erro";

export interface Broadcast {
  id: number;
  texto: string;
  total: number;
  enviados: number;
  falhas: number;
  status: BroadcastStatus;
  criado_por: string | null;
  imagem: string | null; // caminho relativo /media/<arquivo> ou null
  created_at: string;
}

// --- Conversas ------------------------------------------------------------

export type MsgRole = "cliente" | "agente" | "humano" | "nota";

export interface Mensagem {
  role: MsgRole;
  content: string;
  especialista: string | null;
  created_at: string;
}

export interface ConversaResumo {
  thread_id: string;
  cliente: string | null;
  telefone: string | null;
  status: ConversaStatus;
  especialista: string | null;
  unread: number;
  last_preview: string | null;
  responsavel?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversaDetalhe extends ConversaResumo {
  mensagens: Mensagem[];
}

// --- Fila humana ----------------------------------------------------------

export type FilaTipo = "pedido" | "entrega" | "boleto";
export type FilaStatus = "novo" | "andamento" | "concluido";

export interface FilaItem {
  id: number;
  tipo: FilaTipo;
  thread_id: string | null;
  cliente: string | null;
  telefone: string | null;
  resumo: string;
  status: FilaStatus;
  responsavel: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

// --- Métricas -------------------------------------------------------------

export interface MetricaDia {
  dia: string; // ISO date
  atendimentos: number;
  humano: number;
}

export interface Metrics {
  semana: MetricaDia[];
  especialistas: { nome: string; valor: number }[];
  totais: {
    conversas: number;
    atendimentos: number;
    handoffs: number;
    na_fila: number;
    resolvidos_pct: number;
    abertas: number;
    resolvidas: number;
    clientes_total: number;
    clientes_ativos: number;
    opt_outs: number;
    orcamentos_abertos: number;
    campanhas: number;
  };
}

// --- Autenticação & assinatura (SaaS multi-tenant) ---
export interface AssinaturaStatus {
  tem_assinatura: boolean;
  ativa: boolean;
  status: string;
  plan: string | null;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
}

export interface Me {
  email: string;
  nome: string | null;
  name: string | null;
  username: string | null;
  role: string;
  is_staff: boolean;
  whatsapp: string | null;
  verificacoes: { email: boolean; whatsapp: boolean };
  tenant: { id: number; nome: string | null; slug: string | null };
  assinatura: AssinaturaStatus;
}

export interface Plano {
  id: string;
  nome: string;
  preco: number;
  descricao: string;
  disponivel: boolean;
}

// --- Consumo pay-per-use (medição de tokens) ---
export interface UsoTipo {
  tipo: string;
  label: string;
  tokens: number;
  custo: number;
  eventos: number;
}

export interface Uso {
  mes: string;
  tokens: number;
  custo: number;
  eventos: number;
  por_tipo: UsoTipo[];
  cobranca_automatica: boolean;
  precos: { embedding_por_1k: number; chat_por_1k: number };
}

// --- Suporte / Chamados ---
export interface TicketMsg {
  autor: "cliente" | "suporte";
  corpo: string;
  created_at: string;
}

export interface TicketResumo {
  id: number;
  assunto: string;
  categoria: string;
  prioridade: string;
  status: string;
  created_at: string;
  updated_at: string;
  mensagens: number;
}

export interface TicketDetalhe {
  id: number;
  assunto: string;
  categoria: string;
  prioridade: string;
  status: string;
  created_at: string;
  updated_at: string;
  mensagens: TicketMsg[];
}

// --- Central admin (staff/Dew) — cross-tenant ---
export interface AdminOverview {
  tenants: number;
  ativos: number;
  chamados_abertos: number;
  consumo_mes: number;
}

export interface AdminTenant {
  id: number;
  nome: string;
  slug: string;
  tenant_status: string;
  created_at: string;
  plan: string | null;
  sub_status: string | null;
  cancel_at_period_end: boolean | null;
  current_period_end: string | null;
  usuarios: number;
}

export interface AdminPlano {
  id: string;
  nome: string;
  preco: number;
  descricao: string;
  stripe_price_id: string | null;
  assinantes: number;
  updated_by: string | null;
  updated_at: string | null;
}

export interface AdminPlanoHistorico {
  id: number;
  plan_id: string;
  preco_anterior: number | null;
  preco_novo: number;
  stripe_price_id_novo: string | null;
  assinaturas_migradas: number;
  assinaturas_falhas: number;
  alterado_por: string | null;
  created_at: string;
}

export interface AdminPlanos {
  items: AdminPlano[];
  historico: AdminPlanoHistorico[];
  stripe_configurado: boolean;
  resultado?: {
    plano: string;
    preco: number;
    stripe_price_id: string | null;
    assinaturas_migradas: number;
    assinaturas_falhas: number;
  };
}

export interface AdminTicketResumo {
  id: number;
  assunto: string;
  categoria: string;
  prioridade: string;
  status: string;
  created_at: string;
  updated_at: string;
  tenant_id: number;
  tenant_nome: string;
  mensagens: number;
}

export interface AdminTicketDetalhe {
  id: number;
  tenant_id: number;
  assunto: string;
  categoria: string;
  prioridade: string;
  status: string;
  created_at: string;
  updated_at: string;
  tenant_nome: string;
  cliente_email: string | null;
  mensagens: TicketMsg[];
}

export interface AdminConsumoTenant {
  id: number;
  nome: string;
  tokens: number;
  custo: number;
}

// --- Integrações (API pública) ---
export interface ApiEscopo {
  id: string;
  grupo: string;
  label: string;
  descricao: string;
  escrita: boolean;
}

export interface ApiChave {
  id: number;
  tenant_id: number;
  nome: string;
  prefixo: string;
  escopos: string[];
  ips_permitidos: string[];
  rate_limit_min: number;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  created_at: string;
  chamadas_24h?: number;
}

/** Retorno da criação/rotação: o texto puro da chave só vem aqui. */
export interface ApiChaveCriada extends ApiChave {
  chave: string;
}

export interface ApiLog {
  id: number;
  api_key_id: number | null;
  chave: string | null;
  prefixo: string | null;
  metodo: string;
  rota: string;
  status: number;
  duracao_ms: number;
  ip: string | null;
  created_at: string;
}

export interface ApiResumo {
  chamadas_24h: number;
  erros_24h: number;
  chaves_ativas: number;
}

export interface AdminApiChave extends ApiChave {
  tenant_nome: string;
}

// --- Webhooks de saída ---
export interface WebhookEvento {
  id: string;
  grupo: string;
  label: string;
  descricao: string;
  exemplo: Record<string, unknown>;
}

export interface Webhook {
  id: number;
  url: string;
  descricao: string | null;
  eventos: string[];
  ativo: boolean;
  desativado_motivo: string | null;
  falhas_consecutivas: number;
  ultimo_status: number | null;
  ultimo_envio_at: string | null;
  created_at: string;
  entregas_24h?: number;
  falhas_24h?: number;
}

export interface WebhookEntrega {
  id: number;
  webhook_id: number;
  evento_id: string;
  evento: string;
  payload: Record<string, unknown>;
  sucesso: boolean;
  status_code: number | null;
  tentativas: number;
  erro: string | null;
  duracao_ms: number;
  created_at: string;
}

export interface WebhookResultado {
  sucesso: boolean;
  status_code: number | null;
  erro: string | null;
  tentativas: number;
  duracao_ms: number;
}

// --- Central admin: WhatsApp da plataforma (códigos de verificação) ---
export interface AdminWhatsappVerificacao {
  evolution_configurada: boolean;
  instancia: string | null;
  origem: "painel" | "ambiente" | null;
  estado: WhatsappEstado | null;
  numero: string | null;
  perfil: string | null;
  erro: string | null;
}
