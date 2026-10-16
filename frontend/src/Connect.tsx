/** First-run screen: point the app at an API and authenticate with an API key. */
import { useState } from "react";
import { ApiError, createClient } from "./api";
import { useStore } from "./store";
import { Button, Field, I, Input, Spinner, StatusDot } from "./ui";

const DEMO_KEY = "shortly-demo-key-2024";
const DEFAULT_BASE = "https://shortly-url-api.onrender.com";

export default function Connect() {
  const { connect, theme, toggleTheme } = useStore();
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ version: string; redis: boolean | null } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setHealth(null);
    setBusy(true);
    try {
      const base = baseUrl.trim().replace(/\/+$/, "");
      const probe = createClient({ baseUrl: base, apiKey: apiKey.trim() });
      const h = await probe.health();
      if (h.status !== "ok") {
        throw new ApiError(503, "degraded", "The API reports a degraded database — try again shortly.");
      }
      await probe.listLinks({ limit: 1 }); // validates the API key itself
      setHealth({ version: h.version, redis: h.redis });
      connect({ baseUrl: base, apiKey: apiKey.trim() });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Connection failed.";
      setError(msg);
      if (err instanceof ApiError && err.status === 401) {
        // API reachable but key wrong — surface that the endpoint itself is fine.
        setError(`${msg} (API is reachable — check the key)`);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      {/* ambient background */}
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute -top-24 left-1/2 h-72 w-[36rem] -translate-x-1/2 rounded-full bg-emerald-500/15 blur-3xl dark:bg-emerald-500/10" />
        <div className="absolute bottom-0 right-0 h-56 w-56 rounded-full bg-violet-500/10 blur-3xl" />
      </div>

      <button
        onClick={toggleTheme}
        className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-200/60 dark:hover:bg-slate-800"
        aria-label="Toggle theme"
        title="Toggle theme"
      >
        {theme === "dark" ? <I.Sun size={17} /> : <I.Moon size={17} />}
      </button>

      <div className="fade-up card w-full max-w-md">
        <div className="card-pad">
          <div className="mb-6 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-600 text-lg text-white shadow-lg shadow-emerald-600/30">
              ⚡
            </span>
            <div>
              <h1 className="text-xl font-extrabold tracking-tight">Shortly</h1>
              <p className="text-xs text-slate-400">Link shortener · click analytics</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="API base URL" hint="Where the FastAPI service lives.">
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={DEFAULT_BASE}
                spellCheck={false}
                autoCapitalize="off"
                inputMode="url"
                required
              />
            </Field>
            <Field label="API key" hint="Sent as the X-API-Key header; stored only in your browser.">
              <div className="relative">
                <Input
                  className="pr-10"
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="paste your key…"
                  autoComplete="off"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  aria-label={showKey ? "Hide key" : "Show key"}
                >
                  <I.Eye size={15} />
                </button>
              </div>
            </Field>

            {error ? (
              <div className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-600 dark:text-rose-300" role="alert">
                <I.Alert className="mt-0.5 shrink-0" size={14} />
                <span>{error}</span>
              </div>
            ) : null}

            <Button type="submit" variant="primary" className="w-full py-2.5" disabled={busy}>
              {busy ? <Spinner /> : <I.Key size={15} />}
              {busy ? "Connecting…" : "Connect"}
            </Button>

            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <button
                type="button"
                className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-2 hover:text-emerald-500"
                onClick={() => setApiKey(DEMO_KEY)}
              >
                <I.Bolt size={12} /> insert demo key
              </button>
              <a
                href="https://github.com/Dani-Devlop/shortly-url"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 hover:text-emerald-500"
              >
                GitHub <I.External size={11} />
              </a>
            </div>

            {health ? (
              <div className="flex items-center gap-2 rounded-xl bg-emerald-500/10 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-300">
                <StatusDot state="ok" /> connected · v{health.version} · redis {health.redis === null ? "off" : health.redis ? "on" : "down"}
              </div>
            ) : null}
          </form>
        </div>

        <div className="border-t border-slate-100 px-5 py-3 text-center text-[11px] leading-relaxed text-slate-400 dark:border-slate-800">
          Free Render instances sleep — the first connection may take ~30 s to wake the API.
        </div>
      </div>
    </div>
  );
}
