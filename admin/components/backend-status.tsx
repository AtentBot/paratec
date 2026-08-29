"use client";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useEffect, useState } from "react";

type State = "checando" | "online" | "offline";

/** Pinga /health do agent-service e mostra o estado da conexão. */
export function BackendStatus() {
  const [state, setState] = useState<State>("checando");
  const [model, setModel] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function check() {
      try {
        const res = await fetch(`${api.base}/health`, { cache: "no-store" });
        const data = await res.json();
        if (!alive) return;
        setState(data.status === "ok" ? "online" : "offline");
        setModel(data.model ?? null);
      } catch {
        if (alive) setState("offline");
      }
    }
    check();
    const id = setInterval(check, 20000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const color =
    state === "online"
      ? "bg-success"
      : state === "offline"
        ? "bg-danger"
        : "bg-faint";
  const label =
    state === "online"
      ? model
        ? `Agente · ${model}`
        : "Agente online"
      : state === "offline"
        ? "Agente offline"
        : "Verificando…";

  return (
    <div
      className="flex items-center gap-2 rounded-lg border bg-surface px-3 py-1.5 text-xs font-medium text-muted"
      title={`${api.base}`}
    >
      <span className={cn("h-2 w-2 rounded-full", color, state === "online" && "animate-pulse-ring")} />
      {label}
    </div>
  );
}
