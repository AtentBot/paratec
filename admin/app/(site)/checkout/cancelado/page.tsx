import Link from "next/link";
import { XCircle } from "lucide-react";

export default function CheckoutCancelado() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center px-6 py-24 text-center">
      <XCircle size={48} className="text-muted" />
      <h1 className="mt-4 text-2xl font-bold text-ink">Pagamento não concluído</h1>
      <p className="mt-2 text-muted">
        Você cancelou o checkout. Nenhuma cobrança foi feita. Quando quiser, é só
        escolher um plano novamente.
      </p>
      <Link
        href="/precos"
        className="mt-6 rounded-xl bg-feature px-5 py-3 text-sm font-semibold text-feature-fg transition hover:opacity-90"
      >
        Ver planos
      </Link>
    </div>
  );
}
