"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

/** Alterna tema claro/escuro persistindo em localStorage. */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("paratec-theme", next ? "dark" : "light");
    } catch {
      /* ambiente sem storage — ignora */
    }
  }

  return (
    <button
      onClick={toggle}
      aria-label="Alternar tema"
      className="grid h-9 w-9 place-items-center rounded-lg border bg-surface text-muted transition hover:text-ink hover:shadow-card"
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

/** Injetado no <head> para aplicar o tema antes da pintura (evita flash). */
export const themeScript = `
(function(){
  try {
    var t = localStorage.getItem('paratec-theme');
    var d = t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (d) document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`;
