import { WifiOff } from "lucide-react";

/** Exibido quando o agent-service não responde — não inventamos dados. */
export function OfflineNotice({ base }: { base: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger">
      <WifiOff size={14} className="shrink-0" />
      <span>
        Sem conexão com o agent-service ({base}). Suba o backend para ver os dados.
      </span>
    </div>
  );
}

/** Estado vazio genérico (backend online, porém ainda sem registros). */
export function VazioNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed bg-surface-2 px-3 py-2 text-xs text-muted">
      {children}
    </div>
  );
}
