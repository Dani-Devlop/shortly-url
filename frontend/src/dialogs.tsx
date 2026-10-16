/** Dialogs: create/edit link, QR codes, compare two codes, per-link stats. */
import { useEffect, useMemo, useState } from "react";
import type { Api } from "./api";
import { AreaChart, deviceColor, DualChart, HBars, Heatmap, StackedSources } from "./charts";
import { fmtInt, hostOf, pathOf, relTime, tagHue, useStore } from "./store";
import type { CompareResult, DailyStats, Hours, LinkDetail, LinkOut, ReferrerWindow } from "./types";
import { Button, Chip, Field, I, Input, Modal, Select, Spinner } from "./ui";

const WIN_OPTIONS = [7, 14, 30, 90];

function errText(e: unknown): string {
  const anyErr = e as { details?: { loc: string; msg: string }[]; message?: string; status?: number };
  if (anyErr?.details?.length) {
    return anyErr.details.map((d) => `${d.loc.split(".").pop()}: ${d.msg}`).join(" · ");
  }
  return anyErr?.message ?? "Something went wrong.";
}

/* ================= create / edit ================= */

export function LinkFormDialog({
  api,
  edit,
  knownTags,
  onClose,
  onSaved,
}: {
  api: Api;
  edit: LinkOut | null;
  knownTags: string[];
  onClose: () => void;
  onSaved: (link: LinkOut, created: boolean) => void;
}) {
  const { toast } = useStore();
  const [url, setUrl] = useState(edit?.original_url ?? "");
  const [alias, setAlias] = useState("");
  const [tags, setTags] = useState((edit?.tags ?? []).join(", "));
  const [expiry, setExpiry] = useState("");
  const [clearExpiry, setClearExpiry] = useState(false);
  const [utm, setUtm] = useState(edit?.utm_template ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      if (edit) {
        const body: Record<string, unknown> = { tags: tagList };
        if (url !== edit.original_url) body.url = url;
        if (utm !== (edit.utm_template ?? "")) body.utm_template = utm === "" ? null : utm;
        if (clearExpiry) body.expires_at = null;
        else if (expiry) body.expires_at = new Date(expiry).toISOString();
        else if (edit.expires_at) body.expires_at = null;
        const updated = await api.patchLink(edit.code, body);
        toast(`Updated ${updated.code}`, "ok");
        onSaved(updated, false);
      } else {
        const created = await api.shorten({
          url,
          custom_code: alias || undefined,
          tags: tagList,
          utm_template: utm || undefined,
          expires_at: expiry ? new Date(expiry).toISOString() : undefined,
        });
        toast(`Created /${created.code}`, "ok", {
          label: "Copy",
          run: async () => {
            await navigator.clipboard.writeText(created.short_url);
          },
        });
        onSaved(created, true);
      }
      onClose();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={edit ? `Edit /${edit.code}` : "Create a short link"}
      subtitle={edit ? hostOf(edit.original_url) : "Paste a destination URL — get a trackable short link."}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Destination URL">
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/very/long/path" inputMode="url" required />
        </Field>

        {!edit ? (
          <Field label="Custom alias (optional)" hint="4–16 chars · letters, digits, - and _">
            <Input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="launch-2026" spellCheck={false} />
          </Field>
        ) : null}

        <Field label="Tags (optional)" hint={`Comma-separated, up to 6 · spaces become "-"${knownTags.length ? ` · known: ${knownTags.slice(0, 6).join(", ")}` : ""}`}>
          <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="docs, launch" spellCheck={false} />
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={edit ? "New expiry" : "Expires at (optional)"}>
            <Input type="datetime-local" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
          </Field>
          <Field label="UTM template (optional)" hint="e.g. utm_source=newsletter&utm_campaign=launch">
            <Input value={utm} onChange={(e) => setUtm(e.target.value)} placeholder="utm_source=…" spellCheck={false} />
          </Field>
        </div>

        {edit && edit.expires_at ? (
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <input type="checkbox" checked={clearExpiry} onChange={(e) => setClearExpiry(e.target.checked)} className="h-4 w-4 rounded accent-emerald-600" />
            clear current expiry ({relTime(edit.expires_at)})
          </label>
        ) : null}

        {error ? (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-600 dark:text-rose-300" role="alert">
            {error}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? <Spinner /> : <I.Check size={15} />}
            {edit ? "Save changes" : "Create link"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ================= QR ================= */

const QR_PRESETS: [string, string, string][] = [
  ["Ink on white", "111827", "ffffff"],
  ["Emerald", "065f46", "ecfdf5"],
  ["Dark mode", "34d399", "0f172a"],
  ["Violet", "5b21b6", "f5f3ff"],
  ["Amber", "92400e", "fffbeb"],
  ["Rose", "9f1239", "fff1f2"],
];

export function QrDialog({ api, link, onClose }: { api: Api; link: LinkOut; onClose: () => void }) {
  const [size, setSize] = useState(256);
  const [format, setFormat] = useState<"svg" | "png">("png");
  const [fg, setFg] = useState("111827");
  const [bg, setBg] = useState("ffffff");
  const src = api.qrUrl(link.code, { size, fg, bg, format });
  return (
    <Modal open onClose={onClose} title={`QR · /${link.code}`} subtitle="Scan or download — colours are yours to choose.">
      <div className="flex flex-col items-center gap-4">
        <div className="rounded-2xl border border-slate-200 p-3 dark:border-slate-700" style={{ background: `#${bg}` }}>
          {/* cross-origin <img> is fine — no CORS needed for images */}
          <img src={src} alt={`QR code for ${link.code}`} width={220} height={220} className="rounded-lg" />
        </div>
        <div className="grid w-full grid-cols-2 gap-3">
          <Field label="Format">
            <Select value={format} onChange={(e) => setFormat(e.target.value as "svg" | "png")}>
              <option value="png">PNG</option>
              <option value="svg">SVG (vector)</option>
            </Select>
          </Field>
          <Field label="Size">
            <Select value={size} onChange={(e) => setSize(Number(e.target.value))}>
              {[128, 256, 512, 1024].map((s) => (
                <option key={s} value={s}>
                  {s} px
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div>
          <p className="lbl">Colour presets</p>
          <div className="flex flex-wrap gap-2">
            {QR_PRESETS.map(([name, f, b]) => (
              <button
                key={name}
                title={name}
                onClick={() => {
                  setFg(f);
                  setBg(b);
                }}
                className="flex items-center gap-1.5 rounded-full border border-slate-200 py-1 pl-1.5 pr-2.5 text-[11px] text-slate-500 transition-transform hover:scale-105 dark:border-slate-700 dark:text-slate-300"
              >
                <span className="h-4 w-4 rounded-full border border-slate-300/50" style={{ background: `#${f}` }} />
                {name}
              </button>
            ))}
          </div>
        </div>
        <div className="grid w-full grid-cols-2 gap-3">
          <Field label="Ink (fg)">
            <div className="flex items-center gap-2">
              <input type="color" value={`#${fg}`} onChange={(e) => setFg(e.target.value.slice(1))} className="h-9 w-10 cursor-pointer rounded-lg border border-slate-300 bg-transparent p-1 dark:border-slate-700" aria-label="Ink colour" />
              <Input value={fg} onChange={(e) => setFg(e.target.value.replace("#", ""))} className="font-mono text-xs" />
            </div>
          </Field>
          <Field label="Background (bg)">
            <div className="flex items-center gap-2">
              <input type="color" value={`#${bg}`} onChange={(e) => setBg(e.target.value.slice(1))} className="h-9 w-10 cursor-pointer rounded-lg border border-slate-300 bg-transparent p-1 dark:border-slate-700" aria-label="Background colour" />
              <Input value={bg} onChange={(e) => setBg(e.target.value.replace("#", ""))} className="font-mono text-xs" />
            </div>
          </Field>
        </div>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          download={`shortly-${link.code}-qr.${format}`}
          className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-3 py-2.5 text-sm font-medium text-white hover:bg-emerald-500"
        >
          <I.Download size={15} /> Open / download QR
        </a>
        <p className="text-center text-[11px] text-slate-400">If the download is blocked cross-origin, right-click the image → “Save image as…”.</p>
      </div>
    </Modal>
  );
}

/* ================= compare ================= */

export function CompareDialog({ api, codes, onClose }: { api: Api; codes: string[]; onClose: () => void }) {
  const [a, setA] = useState(codes[0] ?? "");
  const [b, setC] = useState(codes[1] ?? "");
  const [days, setDays] = useState(14);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<CompareResult | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setRes(null);
    try {
      setRes(await api.compare([a, b], days));
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  const [first, second] = res?.items ?? [];
  const verdict = useMemo(() => {
    if (!first || !second) return null;
    const d = first.total_clicks - second.total_clicks;
    if (d === 0) return { text: "Dead heat — identical click counts.", lead: null as string | null };
    const winner = d > 0 ? first : second;
    const diff = Math.abs(d);
    const base = Math.min(first.total_clicks, second.total_clicks) || 1;
    return { text: `${winner.code} leads by ${diff} clicks (${Math.round((diff / base) * 100)}% more).`, lead: winner.code };
  }, [first, second]);

  const dayLabels = useMemo(() => {
    if (!res) return [];
    const out: string[] = [];
    const now = new Date();
    for (let i = res.window_days - 1; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      out.push(d.toLocaleDateString(undefined, { month: "short", day: "numeric" }));
    }
    return out;
  }, [res]);

  return (
    <Modal open onClose={onClose} title="Compare two links" subtitle="Daily clicks, side by side.">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto]">
        <Field label="Link A">
          <Select value={a} onChange={(e) => setA(e.target.value)}>
            {codes.map((c) => (
              <option key={c} value={c}>
                /{c}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Link B">
          <Select value={b} onChange={(e) => setC(e.target.value)}>
            {codes.map((c) => (
              <option key={c} value={c}>
                /{c}
              </option>
            ))}
          </Select>
        </Field>
        <div className="sm:pt-6">
          <Button variant="primary" onClick={run} disabled={!a || !b || a === b || busy} className="w-full sm:w-auto">
            {busy ? <Spinner /> : <I.Compare size={15} />} Compare
          </Button>
        </div>
      </div>
      <div className="mt-2">
        <Select value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36">
          {WIN_OPTIONS.map((d) => (
            <option key={d} value={d}>
              last {d} days
            </option>
          ))}
        </Select>
      </div>

      {error ? <div className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-600 dark:text-rose-300">{error}</div> : null}

      {res && first && second ? (
        <div className="fade-up mt-5 space-y-4">
          <DualChart a={first.points} b={second.points} labels={dayLabels} />
          <div className="grid grid-cols-2 gap-3">
            {[first, second].map((it, i) => (
              <div key={it.code} className={`card card-pad ${i === 0 ? "border-l-4 border-l-emerald-500" : "border-l-4 border-l-violet-500"}`}>
                <div className="flex items-center justify-between">
                  <p className="font-mono text-sm font-bold">/{it.code}</p>
                  {verdict?.lead === it.code ? (
                    <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">leads</span>
                  ) : null}
                </div>
                <p className="mt-1 truncate text-[11px] text-slate-400" title={it.original_url}>
                  {hostOf(it.original_url)}
                </p>
                <p className="mt-2 text-2xl font-extrabold tabular-nums">{fmtInt(it.total_clicks)}</p>
                <p className="text-[11px] text-slate-400">clicks · {fmtInt(it.unique_clicks)} unique</p>
              </div>
            ))}
          </div>
          {verdict ? <p className="rounded-xl bg-slate-100 px-3 py-2.5 text-center text-xs font-medium text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">{verdict.text}</p> : null}
        </div>
      ) : null}
    </Modal>
  );
}

/* ================= per-link stats ================= */

export function StatsModal({
  api,
  code,
  onClose,
  onQr,
}: {
  api: Api;
  code: string;
  onClose: () => void;
  onQr: (link: LinkOut) => void;
}) {
  const [days, setDays] = useState(30);
  const [detail, setDetail] = useState<LinkDetail | null>(null);
  const [daily, setDaily] = useState<DailyStats | null>(null);
  const [refs, setRefs] = useState<ReferrerWindow | null>(null);
  const [hours, setHours] = useState<Hours | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useStore();

  useEffect(() => {
    let alive = true;
    setDetail(null);
    setDaily(null);
    setRefs(null);
    setHours(null);
    setError(null);
    (async () => {
      try {
        const d = await api.linkDetail(code);
        if (!alive) return;
        setDetail(d);
        const [dl, rf, hh] = await Promise.all([api.daily(code, days), api.referrers(code, days, 8), api.hours(code, days)]);
        if (!alive) return;
        setDaily(dl);
        setRefs(rf);
        setHours(hh);
      } catch (err) {
        if (alive) setError(errText(err));
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, code, days]);

  const dayLabels = useMemo(() => {
    if (!daily) return [];
    return daily.items.map((p) => new Date(p.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }));
  }, [daily]);

  async function copyShort() {
    if (!detail) return;
    await navigator.clipboard.writeText(detail.short_url);
    toast("Short URL copied", "ok");
  }

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={
        <span className="flex items-center gap-2">
          <span className="font-mono">/{code}</span>
          {detail?.archived ? <Chip className="!bg-amber-500/15 !text-amber-600 dark:!text-amber-300">📦 archived</Chip> : null}
        </span>
      }
      subtitle={
        detail ? (
          <span className="flex flex-wrap items-center gap-2">
            <span title={detail.original_url}>
              {hostOf(detail.original_url)}
              <span className="text-slate-300 dark:text-slate-600">{pathOf(detail.original_url)}</span>
            </span>
            <button onClick={copyShort} className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700" title="Copy short URL">
              <I.Copy size={10} /> {detail.short_url.replace(/^https?:\/\//, "")}
            </button>
          </span>
        ) : (
          "loading…"
        )
      }
    >
      {error ? <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-600 dark:text-rose-300">{error}</div> : null}

      {!detail && !error ? (
        <div className="flex justify-center py-12 text-slate-400">
          <Spinner className="h-6 w-6" />
        </div>
      ) : null}

      {detail ? (
        <div className="space-y-6">
          {/* big numbers + actions */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="card card-pad !p-3">
              <p className="panel-title">Total clicks</p>
              <p className="mt-1 text-2xl font-extrabold tabular-nums">{fmtInt(detail.total_clicks)}</p>
            </div>
            <div className="card card-pad !p-3">
              <p className="panel-title">Unique visitors</p>
              <p className="mt-1 text-2xl font-extrabold tabular-nums">{fmtInt(detail.unique_clicks)}</p>
            </div>
            <div className="card card-pad !p-3">
              <p className="panel-title">Created</p>
              <p className="mt-1 text-sm font-semibold">{relTime(detail.created_at)}</p>
            </div>
            <div className="card card-pad !p-3">
              <p className="panel-title">Expires</p>
              <p className="mt-1 text-sm font-semibold">{detail.expires_at ? relTime(detail.expires_at) : "never"}</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <a href={detail.short_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 px-3 py-1.5 text-xs font-medium hover:border-emerald-500 hover:text-emerald-600 dark:border-slate-700 dark:hover:border-emerald-500 dark:hover:text-emerald-400">
              <I.External size={13} /> Open short URL
            </a>
            <Button variant="outline" className="!py-1.5 text-xs" onClick={() => onQr(detail)}>
              <I.Qr size={13} /> QR
            </Button>
            <a href={api.statsCsvUrl(detail.code)} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 px-3 py-1.5 text-xs font-medium hover:border-emerald-500 hover:text-emerald-600 dark:border-slate-700 dark:hover:border-emerald-500 dark:hover:text-emerald-400">
              <I.Download size={13} /> Clicks CSV
            </a>
            {detail.tags.map((t) => (
              <Chip key={t} hue={tagHue(t)}>
                #{t}
              </Chip>
            ))}
          </div>

          {/* window selector */}
          <div className="flex items-center gap-2">
            <span className="panel-title">Window</span>
            {WIN_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                  days === d ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>

          {/* daily chart */}
          <section>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="panel-title">Daily clicks</h3>
              {daily ? <span className="text-[11px] tabular-nums text-slate-400">{fmtInt(daily.total)} in {daily.window_days}d</span> : null}
            </div>
            {daily ? <AreaChart points={daily.items.map((p) => p.clicks)} labels={dayLabels} /> : <ChartSkeleton />}
          </section>

          {/* devices */}
          <section>
            <h3 className="panel-title mb-2">Devices · all-time</h3>
            {detail.device_breakdown.length ? (
              <HBars items={detail.device_breakdown.map((d) => ({ label: d.device, value: d.clicks, color: deviceColor(d.device) }))} />
            ) : (
              <p className="text-xs text-slate-400">No clicks yet.</p>
            )}
          </section>

          {/* referrers × device */}
          <section>
            <h3 className="panel-title mb-2">Traffic sources · {days}d</h3>
            {refs ? <StackedSources items={refs.items} /> : <ChartSkeleton />}
          </section>

          {/* heatmap */}
          <section>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="panel-title">When · {days}d (UTC)</h3>
              {hours ? (
                <span className="text-[11px] tabular-nums text-slate-400">
                  {fmtInt(hours.total)} clicks · peak {hours.peak}
                </span>
              ) : null}
            </div>
            {hours ? <Heatmap cells={hours.cells} peak={hours.peak} /> : <ChartSkeleton />}
          </section>

          {/* recent clicks */}
          <section>
            <h3 className="panel-title mb-2">Recent clicks</h3>
            {detail.recent_clicks.length ? (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {detail.recent_clicks.slice(0, 10).map((c, i) => (
                  <li key={i} className="flex items-center gap-3 py-2 text-xs">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: deviceColor(c.device) }} title={c.device} />
                    <span className="w-20 shrink-0 font-medium capitalize">{c.device}</span>
                    <span className="min-w-0 flex-1 truncate text-slate-500 dark:text-slate-400">{c.referrer ?? "direct"}</span>
                    <span className="shrink-0 font-mono text-[10px] text-slate-400">{c.ip_hash ?? "—"}</span>
                    <span className="w-16 shrink-0 text-right text-slate-400">{relTime(c.clicked_at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-400">No clicks recorded yet — share the short URL!</p>
            )}
          </section>
        </div>
      ) : null}
    </Modal>
  );
}

function ChartSkeleton() {
  return <div className="h-28 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800/60" />;
}
