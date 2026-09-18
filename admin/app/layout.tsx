import type { Metadata } from "next";
import { headers } from "next/headers";
import { themeScript } from "@/components/theme-toggle";
import "./globals.css";

export const metadata: Metadata = {
  title: "AtentBot · Atendimento com IA no WhatsApp",
  description:
    "Plataforma de atendimento e vendas por IA no WhatsApp para distribuidores e PMEs.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Nonce da CSP (definido no middleware) para liberar o script inline do tema.
  const nonce = headers().get("x-nonce") ?? undefined;
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
