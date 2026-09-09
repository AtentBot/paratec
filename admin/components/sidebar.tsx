"use client";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  LayoutDashboard,
  MessagesSquare,
  Package,
  Headset,
  Users,
  UserCog,
  ClipboardList,
  Megaphone,
  FileBarChart,
  BookOpen,
  Bot,
  Bell,
  BellOff,
  Settings,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

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
  { href: "/equipe", label: "Equipe de vendas", icon: UserCog },
  { href: "/orcamentos", label: "Orçamentos", icon: ClipboardList },
  { href: "/catalogo", label: "Catálogo", icon: Package },
  { href: "/fila", label: "Fila humana", icon: Headset },
  { href: "/promocoes", label: "Promoções", icon: Megaphone },
  { href: "/conhecimento", label: "Conhecimento", icon: BookOpen },
  { href: "/relatorios", label: "Relatórios", icon: FileBarChart },
];

const SISTEMA: NavItem[] = [
  { href: "/agentes", label: "Agentes", icon: Bot },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

function NavLink({ item, path }: { item: NavItem; path: string }) {
  const { href, label, icon: Icon, badge } = item;
  const active = href === "/" ? path === "/" : path.startsWith(href);
  return (
    <Link
      href={href}
      className={cn(
        "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
        active
          ? "bg-accent-soft text-accent-ink"
          : "text-muted hover:bg-surface-2 hover:text-ink",
      )}
    >
      {active && <span className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-accent" />}
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
}

// Bipe curto (WebAudio) — sem depender de arquivo de áudio.
function beep() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.26);
    osc.onended = () => ctx.close();
  } catch {
    /* áudio bloqueado pelo navegador — ignora */
  }
}

export function Sidebar() {
  const path = usePathname();

  // Indicador global de não-lidas (badge no menu Atendimento) + som opcional.
  const [unread, setUnread] = useState(0);
  const [som, setSom] = useState(false);
  const somRef = useRef(false);
  const prevUnread = useRef<number | null>(null);

  useEffect(() => {
    try {
      const on = localStorage.getItem("paratec_som_msg") === "1";
      setSom(on);
      somRef.current = on;
    } catch {
      /* localStorage indisponível */
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const { total } = await api.unreadTotal();
        if (!alive) return;
        if (prevUnread.current !== null && total > prevUnread.current && somRef.current) {
          beep();
        }
        prevUnread.current = total;
        setUnread(total);
      } catch {
        /* backend fora do ar — mantém o valor atual */
      }
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  function toggleSom() {
    const novo = !som;
    setSom(novo);
    somRef.current = novo;
    try {
      localStorage.setItem("paratec_som_msg", novo ? "1" : "0");
    } catch {
      /* localStorage indisponível */
    }
    if (novo) beep(); // toca uma vez p/ "destravar" o áudio no navegador
  }

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
        {NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item.href === "/conversas" ? { ...item, badge: unread || undefined } : item}
            path={path}
          />
        ))}

        <p className="px-3 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Sistema
        </p>
        {SISTEMA.map((item) => (
          <NavLink key={item.href} item={item} path={path} />
        ))}
      </nav>

      <div className="border-t px-4 py-3">
        <button
          onClick={toggleSom}
          title={som ? "Som de novas mensagens: ligado" : "Som de novas mensagens: desligado"}
          className="mb-1 flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          {som ? <Bell size={15} className="text-accent-ink" /> : <BellOff size={15} className="text-faint" />}
          <span className="flex-1 text-left">Som de novas mensagens</span>
          <span
            className={cn(
              "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
              som ? "bg-accent-soft text-accent-ink" : "bg-surface-2 text-faint",
            )}
          >
            {som ? "ON" : "OFF"}
          </span>
        </button>
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
