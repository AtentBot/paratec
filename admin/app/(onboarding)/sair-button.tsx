"use client";

import { api } from "@/lib/api";
import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

export function SairButton() {
  const router = useRouter();
  async function sair() {
    try {
      await api.logout();
    } catch {
      /* ignora */
    }
    router.push("/login");
  }
  return (
    <button
      onClick={sair}
      className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-muted transition hover:text-danger"
    >
      <LogOut size={15} /> Sair
    </button>
  );
}
