import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Marca } from "../(site)/_components/marca";
import { SairButton } from "./sair-button";

// Shell do ONBOARDING (logado, sem plano ativo): sem sidebar nem acesso ao painel.
export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="site flex min-h-dvh flex-col bg-bg">
      <header className="border-b bg-bg">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <Link href="/" aria-label="AtentBot, página inicial" className="shrink-0 rounded-lg">
            <Marca nomeClassName="hidden min-[400px]:block" />
          </Link>
          <div className="ml-auto flex items-center gap-1">
            <SairButton />
            <ThemeToggle />
          </div>
        </div>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
