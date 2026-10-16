/** Typed API client — every method maps 1:1 onto a FastAPI endpoint. */
import type {
  Activity,
  BulkActionOut,
  CompareResult,
  DailyStats,
  DeviceBreakdown,
  Health,
  Hours,
  LinkDetail,
  LinkOut,
  LinkPageEnv,
  PatchBody,
  ReferrerWindow,
  ShortenBody,
  Sparklines,
  Stats,
  TagRollup,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: { loc: string; msg: string; type: string }[];

  constructor(status: number, code: string, message: string, details?: ApiError["details"]) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface ApiConfig {
  baseUrl: string;
  apiKey: string;
}

function normalizeBase(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

async function request<T>(cfg: ApiConfig, path: string, init?: RequestInit): Promise<T> {
  const base = normalizeBase(cfg.baseUrl);
  let res: Response;
  try {
    res = await fetch(base + path, {
      ...init,
      headers: {
        "X-API-Key": cfg.apiKey,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach ${base} — check the API URL and that the service is awake (free Render instances may take ~30s to wake).`);
  }
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; details?: ApiError["details"] } })?.error;
    if (res.status === 401) {
      throw new ApiError(401, err?.code ?? "unauthorized", "Invalid API key.");
    }
    throw new ApiError(
      res.status,
      err?.code ?? "http_error",
      err?.message ?? `Request failed (${res.status})`,
      err?.details,
    );
  }
  return body as T;
}

const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
};

export const createClient = (cfg: ApiConfig) => ({
  // --- health ---
  health: () => request<Health>(cfg, "/health"),

  // --- links ---
  listLinks: (o: { limit?: number; offset?: number; status?: string; tag?: string } = {}) =>
    request<LinkPageEnv>(cfg, `/api/links${qs({ limit: o.limit ?? 20, offset: o.offset ?? 0, status: o.status ?? "active", tag: o.tag })}`),
  shorten: (body: ShortenBody) =>
    request<LinkOut>(cfg, "/api/shorten", { method: "POST", body: JSON.stringify(body) }),
  linkDetail: (code: string) => request<LinkDetail>(cfg, `/api/links/${encodeURIComponent(code)}`),
  patchLink: (code: string, body: PatchBody) =>
    request<LinkOut>(cfg, `/api/links/${encodeURIComponent(code)}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteLink: (code: string) =>
    request<void>(cfg, `/api/links/${encodeURIComponent(code)}`, { method: "DELETE" }),
  setArchived: (code: string, archived: boolean) =>
    request<LinkOut>(cfg, `/api/links/${encodeURIComponent(code)}/${archived ? "archive" : "restore"}`, { method: "POST" }),
  bulkAction: (action: "archive" | "restore" | "delete", codes: string[]) =>
    request<BulkActionOut>(cfg, "/api/links/bulk-action", {
      method: "POST",
      body: JSON.stringify({ action, codes }),
    }),

  // --- stats (global panels) ---
  sparklines: (days = 14, limit = 8) => request<Sparklines>(cfg, `/api/stats/sparklines${qs({ days, limit })}`),
  devices: (days = 30, excludeBots = false) =>
    request<DeviceBreakdown>(cfg, `/api/stats/devices${qs({ days, exclude_bots: excludeBots || undefined })}`),
  activity: (limit = 12) => request<Activity>(cfg, `/api/stats/activity${qs({ limit })}`),
  tagRollup: (days = 30) => request<TagRollup>(cfg, `/api/stats/tags${qs({ days })}`),
  compare: (codes: string[], days = 14) =>
    request<CompareResult>(cfg, `/api/stats/compare${qs({ codes: codes.join(","), days })}`),

  // --- stats (per link) ---
  stats: (code: string) => request<Stats>(cfg, `/api/stats/${encodeURIComponent(code)}`),
  daily: (code: string, days = 30) => request<DailyStats>(cfg, `/api/stats/${encodeURIComponent(code)}/daily${qs({ days })}`),
  referrers: (code: string, days = 30, limit = 8) =>
    request<ReferrerWindow>(cfg, `/api/stats/${encodeURIComponent(code)}/referrers${qs({ days, limit })}`),
  hours: (code: string, days = 30) => request<Hours>(cfg, `/api/stats/${encodeURIComponent(code)}/hours${qs({ days })}`),

  // --- asset URLs (used directly by <img>/<a>, no CORS needed) ---
  qrUrl: (code: string, o: { size?: number; fg?: string; bg?: string; format?: "svg" | "png" } = {}) =>
    `${normalizeBase(cfg.baseUrl)}/${encodeURIComponent(code)}/qr${qs({
      size: o.size ?? 256,
      fg: o.fg ? o.fg.replace("#", "") : undefined,
      bg: o.bg ? o.bg.replace("#", "") : undefined,
      format: o.format ?? "svg",
    })}`,
  linksCsvUrl: () => `${normalizeBase(cfg.baseUrl)}/api/links/export`,
  tagCsvUrl: () => `${normalizeBase(cfg.baseUrl)}/api/stats/tags/export`,
  statsCsvUrl: (code: string) => `${normalizeBase(cfg.baseUrl)}/api/stats/${encodeURIComponent(code)}/export`,
});

export type Api = ReturnType<typeof createClient>;
