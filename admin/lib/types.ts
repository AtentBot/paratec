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
