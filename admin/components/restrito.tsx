import { ShieldAlert } from "lucide-react";

export function Restrito() {
  return (
    <div className="rounded-2xl border bg-surface p-10 text-center shadow-card">
      <ShieldAlert size={28} className="mx-auto text-faint" />
      <p className="mt-3 text-sm font-medium text-ink">Acesso restrito</p>
      <p className="text-xs text-muted">Esta área é exclusiva da equipe de administração.</p>
    </div>
  );
}
