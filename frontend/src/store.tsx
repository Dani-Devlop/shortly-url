/** Global client state: connection config, theme, toasts. */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createClient, type Api, type ApiConfig } from "./api";

const CFG_KEY = "shortly.cfg";
const THEME_KEY = "shortly.theme";

export interface Toast {
  id: number;
  kind: "ok" | "err" | "info";
  text: string;
  action?: { label: string; run: () => void | Promise<void> };
}

interface Store {
  cfg: ApiConfig | null;
  api: Api | null;
  theme: "dark" | "light";
  toggleTheme: () => void;
  connect: (cfg: ApiConfig) => void;
  disconnect: () => void;
  toasts: Toast[];
  toast: (text: string, kind?: Toast["kind"], action?: Toast["action"]) => void;
  dismiss: (id: number) => void;
}

const Ctx = createContext<Store | null>(null);

function loadCfg(): ApiConfig | null {
  try {
    const raw = localStorage.getItem(CFG_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ApiConfig;
    if (parsed?.baseUrl && parsed?.apiKey) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<ApiConfig | null>(loadCfg);
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    typeof document !== "undefined" && document.documentElement.classList.contains("dark") ? "dark" : "light",
  );
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (text: string, kind: Toast["kind"] = "ok", action?: Toast["action"]) => {
      const id = nextId.current++;
      setToasts((ts) => [...ts.slice(-3), { id, kind, text, action }]);
      window.setTimeout(() => dismiss(id), action ? 7000 : 3500);
    },
    [dismiss],
  );

  const store = useMemo<Store>(
    () => ({
      cfg,
      api: cfg ? createClient(cfg) : null,
      theme,
      toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
      connect: (c) => {
        setCfg(c);
        try {
          localStorage.setItem(CFG_KEY, JSON.stringify(c));
        } catch {
          /* ignore */
        }
      },
      disconnect: () => {
        setCfg(null);
        try {
          localStorage.removeItem(CFG_KEY);
        } catch {
          /* ignore */
        }
      },
      toasts,
      toast,
      dismiss,
    }),
    [cfg, theme, toasts, toast, dismiss],
  );

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore must be used inside AppProvider");
  return s;
}

/* ---------- formatting helpers ---------- */

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const abs = Math.abs(diff);
  const table: [number, string][] = [
    [60_000, "s"],
    [3_600_000, "m"],
    [86_400_000, "h"],
    [2_592_000_000, "d"],
  ];
  if (abs < 45_000) return diff >= 0 ? "just now" : "soon";
  if (abs < table[1][0]) return `${Math.round(abs / 1000)}s ${diff >= 0 ? "ago" : "ahead"}`;
  if (abs < table[2][0]) return `${Math.round(abs / table[1][0])}m ${diff >= 0 ? "ago" : "ahead"}`;
  if (abs < table[3][0]) return `${Math.round(abs / table[2][0])}h ${diff >= 0 ? "ago" : "ahead"}`;
  if (abs < 315_360_000_000) return `${Math.round(abs / table[3][0])}d ${diff >= 0 ? "ago" : "ahead"}`;
  return new Date(iso).toLocaleDateString();
}

export function fmtInt(n: number): string {
  return n.toLocaleString("en-US");
}

/** Deterministic pastel-ish hue for a tag name (same algorithm spirit as the backend). */
export function tagHue(tag: string): number {
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) % 360;
  return h;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function pathOf(url: string): string {
  try {
    const u = new URL(url);
    const p = u.pathname + u.search;
    return p === "/" ? "" : p;
  } catch {
    return "";
  }
}
