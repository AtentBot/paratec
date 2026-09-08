"use client";

import { cn } from "@/lib/cn";
import {
  LayoutDashboard,
  MessagesSquare,
  Package,
  Headset,
  Users,
  ClipboardList,
  Megaphone,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  badge?: number;
};

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/conversas", label: "Atendimento", icon: MessagesSquare },
  { href: "/clientes", label: "Clientes", icon: Users },
  { href: "/orcamentos", label: "Orçamentos", icon: ClipboardList },
  { href: "/catalogo", label: "Catálogo", icon: Package },
  { href: "/fila", label: "Fila humana", icon: Headset },
  { href: "/promocoes", label: "Promoções", icon: Megaphone },
];

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="sticky top-0 flex h-dvh w-[248px] shrink-0 flex-col border-r bg-surface">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-feature text-accent shadow-card">
          <Zap size={18} className="fill-accent" />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold tracking-tight text-ink">Paratec</p>
          <p className="text-[11px] text-muted">Central de atendimento</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
        <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Operação
        </p>
        {NAV.map(({ href, label, icon: Icon, badge }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                active
                  ? "bg-accent-soft text-accent-ink"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              {active && (
                <span className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-accent" />
              )}
              <Icon
                size={18}
                className={cn(active ? "text-accent-ink" : "text-faint group-hover:text-ink")}
              />
              <span className="flex-1">{label}</span>
              {badge ? (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-danger px-1.5 text-[11px] font-semibold text-white">
                  {badge}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>

      <div className="border-t px-4 py-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink">
            DB
          </span>
          <div className="min-w-0 leading-tight">
            <p className="truncate text-xs font-medium text-ink">Douglas Braga</p>
            <p className="truncate text-[11px] text-muted">Administrador</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
