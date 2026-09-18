"use client";

import { Card } from "@/components/ui";
import type { WhatsappQrCode } from "@/lib/types";
import { CheckCircle2, Loader2, RefreshCw, X } from "lucide-react";

export type QrView = { nome: string; qrcode: WhatsappQrCode; conectado: boolean };

/** Painel de pareamento por QR Code (Configurações e central admin). */
export function QrPanel({
  qr,
  onFechar,
  onRenovar,
}: {
  qr: QrView;
  onFechar: () => void;
  onRenovar: () => void;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">
          Conectar <span className="font-mono text-accent-ink">{qr.nome}</span>
        </h3>
        <button onClick={onFechar} className="text-faint transition hover:text-ink">
          <X size={16} />
        </button>
      </div>

      {qr.conectado ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <CheckCircle2 size={40} className="text-success" />
          <p className="text-sm font-semibold text-ink">Número conectado com sucesso!</p>
          <p className="max-w-xs text-xs text-muted">
            O WhatsApp já está sincronizado com a Evolution e pronto para uso.
          </p>
          <button
            onClick={onFechar}
            className="mt-2 rounded-lg bg-accent px-3.5 py-2 text-xs font-medium text-accent-ink transition hover:opacity-90"
          >
            Concluir
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4 md:flex-row md:items-start">
          <div className="grid h-52 w-52 shrink-0 place-items-center rounded-xl border bg-white p-2">
            {qr.qrcode.base64 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr.qrcode.base64} alt="QR Code de conexão" className="h-full w-full" />
            ) : (
              <div className="flex flex-col items-center gap-2 text-faint">
                <Loader2 size={22} className="animate-spin" />
                <span className="text-[11px]">gerando QR…</span>
              </div>
            )}
          </div>
          <div className="flex-1 text-xs leading-relaxed text-muted">
            <p className="mb-2 flex items-center gap-1.5 font-medium text-ink">
              <Loader2 size={13} className="animate-spin text-warning" />
              Aguardando leitura…
            </p>
            <ol className="ml-4 list-decimal space-y-1.5">
              <li>Abra o WhatsApp no celular do número que quer conectar.</li>
              <li>
                Toque em <strong className="text-ink">Aparelhos conectados</strong> →{" "}
                <strong className="text-ink">Conectar um aparelho</strong>.
              </li>
              <li>Aponte a câmera para este QR Code.</li>
            </ol>
            {qr.qrcode.pairing_code && (
              <p className="mt-3">
                Ou use o código de pareamento:{" "}
                <code className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink ring-1 ring-inset ring-border">
                  {qr.qrcode.pairing_code}
                </code>
              </p>
            )}
            <button
              onClick={onRenovar}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
            >
              <RefreshCw size={12} /> Gerar novo QR Code
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
