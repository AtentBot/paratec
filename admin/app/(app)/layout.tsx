import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { AccountGate } from "@/components/account-gate";

// Layout do PAINEL (autenticado e PAGO). O middleware barra quem não tem cookie;
// <AccountGate/> só renderiza o painel com sessão válida e assinatura ativa
// (senão manda ao /login ou à escolha de plano em /ativar).
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AccountGate>
      <div className="flex min-h-dvh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="mx-auto w-full max-w-[1200px] flex-1 px-6 py-6">{children}</main>
        </div>
      </div>
    </AccountGate>
  );
}
