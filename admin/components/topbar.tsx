"use client";

import { usePathname } from "next/navigation";
import { Search } from "lucide-react";
import { BackendStatus } from "./backend-status";
import { ThemeToggle } from "./theme-toggle";

const TITLES: Record<string, { title: string; sub: string }> = {
  "/": { title: "Dashboard", sub: "Visão geral do atendimento" },
  "/conversas": { title: "Conversas", sub: "Atendimentos no WhatsApp" },
  "/catalogo": { title: "Catálogo", sub: "Produtos, variantes e categorias" },
  "/fila": { title: "Fila humana", sub: "Pedidos, entregas e boletos" },
};

export function Topbar() {
  const path = usePathname();
  const key = path === "/" ? "/" : "/" + path.split("/")[1];
  const meta = TITLES[key] ?? { title: "Paratec", sub: "" };

  return (
    <header className="sticky top-0 z-20 flex items-center gap-4 border-b bg-bg/80 px-6 py-3.5 backdrop-blur-md">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold tracking-tight text-ink">
          {meta.title}
        </h1>
        <p className="truncate text-xs text-muted">{meta.sub}</p>
      </div>

      <div className="ml-auto hidden items-center md:flex">
        <div className="relative">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            placeholder="Buscar…"
            className="w-56 rounded-lg border bg-surface py-2 pl-9 pr-3 text-sm text-ink outline-none transition placeholder:text-faint focus:w-64 focus:ring-2 focus:ring-accent/40"
          />
        </div>
      </div>

      <BackendStatus />
      <ThemeToggle />
    </header>
  );
}
