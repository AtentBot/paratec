import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { AccountGate } from "@/components/account-gate";

// Layout do PAINEL (autenticado). O acesso é protegido pelo middleware (cookie
// de sessão) e revalidado no cliente por <AccountGate/>, que também mostra o
// aviso de assinatura inativa e faz o redirect ao /login se a sessão expirou.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-6 py-6">
          <AccountGate />
          {children}
        </main>
      </div>
    </div>
  );
}
