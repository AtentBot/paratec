import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Marca } from "./_components/marca";

const focus =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

// Shell PÚBLICO (marketing/auth): sem sidebar. Cabeçalho enxuto + rodapé.
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="site flex min-h-dvh flex-col bg-bg">
      <header className="sticky top-0 z-20 border-b bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <Link href="/" aria-label="AtentBot, página inicial" className={"shrink-0 rounded-lg " + focus}>
            <Marca nomeClassName="hidden min-[400px]:block" />
          </Link>

          <nav className="ml-auto flex items-center gap-1 text-[15px]" aria-label="Principal">
            <Link href="/#como-funciona" className={"hidden rounded-full px-3.5 py-2 font-medium text-muted transition hover:text-ink md:block " + focus}>
              Como funciona
            </Link>
            <Link href="/#planos" className={"hidden rounded-full px-3.5 py-2 font-medium text-muted transition hover:text-ink sm:block " + focus}>
              Planos
            </Link>
            <Link href="/#perguntas" className={"hidden rounded-full px-3.5 py-2 font-medium text-muted transition hover:text-ink md:block " + focus}>
              Perguntas
            </Link>
            <span className="mx-2 hidden h-5 w-px bg-border md:block" aria-hidden />
            <Link href="/login" className={"whitespace-nowrap rounded-full border bg-surface px-3 py-2 font-semibold sm:px-4 text-ink transition hover:bg-surface-2 " + focus}>
              Entrar
            </Link>
            <Link href="/cadastro" className={"whitespace-nowrap rounded-full bg-feature px-3 py-2 font-semibold sm:px-4 text-feature-fg transition hover:opacity-90 " + focus}>
              Criar conta
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      <div className="flex-1">{children}</div>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10 text-sm text-muted md:flex-row md:items-start md:justify-between">
          <div>
            <Marca tamanho="lg" />
            <p className="mt-3">Atendimento com inteligência, no WhatsApp da sua empresa.</p>
            <p className="mt-4 text-xs text-faint">© {new Date().getFullYear()} AtentBot</p>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-2" aria-label="Rodapé">
            <Link href="/#planos" className="hover:text-ink">Planos</Link>
            <Link href="/cobranca" className="hover:text-ink">Regras de cobrança</Link>
            <Link href="/confidencialidade" className="hover:text-ink">Confidencialidade</Link>
            <a href="mailto:contato@dewconsultoria.com.br" className="hover:text-ink">Contato</a>
            <Link href="/login" className="hover:text-ink">Entrar</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
