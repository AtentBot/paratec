import type { Config } from "tailwindcss";

/**
 * Cores expostas como CSS variables (ver app/globals.css) para permitir
 * troca de tema (claro/escuro) sem recompilar. O acento "raio" (âmbar/ouro)
 * remete ao domínio da Paratec: proteção contra descargas atmosféricas.
 */
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        faint: "var(--faint)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        "accent-ink": "var(--accent-ink)",
        feature: "var(--feature-bg)",
        "feature-fg": "var(--feature-fg)",
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        info: "var(--info)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        lg: "0.75rem",
        xl: "1rem",
        "2xl": "1.25rem",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
        lift: "0 6px 24px -8px rgb(15 23 42 / 0.18)",
        glow: "0 0 0 1px var(--accent-soft), 0 8px 30px -12px var(--accent)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 var(--accent-soft)" },
          "70%": { boxShadow: "0 0 0 6px transparent" },
          "100%": { boxShadow: "0 0 0 0 transparent" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out both",
        "pulse-ring": "pulse-ring 2s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
