import Link from "next/link";
import { Zap } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

// Shell PÚBLICO (marketing/auth): sem sidebar. Cabeçalho enxuto + rodapé.
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="sticky top-0 z-20 border-b bg-bg/80 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-6 py-3.5">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-feature text-accent shadow-card">
              <Zap size={18} className="fill-accent" />
            </span>
            <span className="text-base font-semibold tracking-tight text-ink">AtentBot</span>
          </Link>
          <nav className="ml-auto flex items-center gap-1 text-sm">
            <Link href="/precos" className="rounded-lg px-3 py-2 font-medium text-muted transition hover:bg-surface-2 hover:text-ink">
              Planos
            </Link>
            <Link href="/login" className="rounded-lg px-3 py-2 font-medium text-muted transition hover:bg-surface-2 hover:text-ink">
              Entrar
            </Link>
            <Link href="/cadastro" className="rounded-lg bg-feature px-3.5 py-2 font-semibold text-feature-fg transition hover:opacity-90">
              Criar conta
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      <div className="flex-1">{children}</div>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-6 text-xs text-muted">
          <span>© {new Date().getFullYear()} AtentBot · Atendimento com IA no WhatsApp</span>
          <span className="flex flex-wrap gap-4">
            <Link href="/precos" className="hover:text-ink">Planos</Link>
            <Link href="/cobranca" className="hover:text-ink">Regras de cobrança</Link>
            <Link href="/confidencialidade" className="hover:text-ink">Confidencialidade</Link>
            <a href="mailto:contato@dewconsultoria.com.br" className="hover:text-ink">Contato</a>
            <Link href="/login" className="hover:text-ink">Entrar</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
