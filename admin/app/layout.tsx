import type { Metadata } from "next";
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
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
