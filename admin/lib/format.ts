// Helpers de apresentação (datas relativas, iniciais, rótulos).

const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

/** Rótulo curto do dia da semana a partir de uma data ISO (para o gráfico). */
export function diaSemana(iso: string): string {
  const d = new Date(iso);
  return DIAS[d.getDay()] ?? "";
}

/** HH:MM de um timestamp ISO. */
export function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Tempo relativo curto ("agora", "12 min", "3 h", "2 d"). */
export function relativo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

/** Iniciais (até 2) de um nome; cai no telefone/thread quando sem nome. */
export function iniciais(nome?: string | null, fallback = "?"): string {
  if (!nome) return fallback.slice(0, 2).toUpperCase();
  const partes = nome.trim().split(/\s+/).slice(0, 2);
  return partes.map((p) => p[0]).join("").toUpperCase() || fallback;
}

export const especialistaLabel: Record<string, string> = {
  produtos: "Produtos",
  pedidos: "Pedidos",
  entrega: "Entrega",
  boletos: "Boletos",
};
