/** Main dashboard: stats strip, link table with bulk actions, analytics panels. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Api } from "./api";
import { deviceColor, HBars, Sparkline, StackedSources } from "./charts";
import { CompareDialog, LinkFormDialog, QrDialog, StatsModal } from "./dialogs";
import { fmtInt, hostOf, pathOf, relTime, tagHue, useStore } from "./store";
import type { Activity, DeviceBreakdown, LinkOut, LinkPageEnv, Sparklines, TagRollup } from "./types";
import {
  Button,
  Chip,
  ClicksBadge,
  cx,
  Empty,
  I,
  IconBtn,
  Input,
  Modal,
  Select,
  Spinner,
  StatusDot,
} from "./ui";

type Status = "active" | "archived" | "all";

interface Dialogs {
  create: boolean;
  edit: LinkOut | null;
  stats: string | null;
  qr: LinkOut | null;
  compare: boolean;
}

export default function Dashboard({ api, onDisconnect }: { api: Api; onDisconnect: () => void }) {
  const { toast, theme, toggleTheme } = useStore();

  // --- list state ---
  const [status, setStatus] = useState<Status>("active");
  const [tag, setTag] = useState("");
  const [search, setSearch] = useState("");
  const [perPage, setPerPage] = useState(10);
  const [page, setPage] = useState(0);
  const [data, setData] = useState<LinkPageEnv | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState<{ codes: string[]; bulk: boolean } | null>(null);

  // --- panel state ---
  const [spark, setSpark] = useState<Sparklines | null>(null);
  const [devices, setDevices] = useState<DeviceBreakdown | null>(null);
  const [excludeBots, setExcludeBots] = useState(true);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [tags, setTags] = useState<TagRollup | null>(null);
  const [health, setHealth] = useState<"ok" | "bad" | "unknown">("unknown");
  const [healthInfo, setHealthInfo] = useState<string>("");

  const [dialogs, setDialogs] = useState<Dialogs>({ create: false, edit: null, stats: null, qr: null, compare: false });
  const searchRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  /* ---------- data loading ---------- */
  useEffect(() => {
    let alive = true;
    setListLoading(true);
    api
      .listLinks({ limit: perPage, offset: page * perPage, status, tag: tag || undefined })
      .then((d) => {
        if (alive) {
          setData(d);
          setListErr(null);
        }
      })
      .catch((e) => alive && setListErr((e as Error).message))
      .finally(() => alive && setListLoading(false));
    return () => {
      alive = false;
    };
  }, [api, perPage, page, status, tag, refreshKey]);

  useEffect(() => {
    let alive = true;
    api.sparklines(14, 8).then((s) => alive && setSpark(s)).catch(() => undefined);
    api.devices(30, excludeBots).then((d) => alive && setDevices(d)).catch(() => undefined);
    api.activity(10).then((a) => alive && setActivity(a)).catch(() => undefined);
    api.tagRollup(30).then((t) => alive && setTags(t)).catch(() => undefined);
    api
      .health()
      .then((h) => {
        if (!alive) return;
        setHealth(h.status === "ok" ? "ok" : "bad");
        setHealthInfo(`v${h.version} · db ${h.database ? "ok" : "down"} · redis ${h.redis === null ? "off" : h.redis ? "ok" : "down"}`);
      })
      .catch(() => alive && setHealth("bad"));
    return () => {
      alive = false;
    };
  }, [api, excludeBots, refreshKey]);

  /* ---------- keyboard shortcuts ---------- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || dialogs.stats || dialogs.edit || dialogs.create || dialogs.qr || dialogs.compare) return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      } else if (e.key === "n") {
        e.preventDefault();
        setDialogs((d) => ({ ...d, create: true }));
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [dialogs]);

  /* ---------- deep link #/link=code ---------- */
  useEffect(() => {
    const m = window.location.hash.match(/^#\/link=([A-Za-z0-9_-]+)$/);
    if (m) {
      setDialogs((d) => ({ ...d, stats: m[1] }));
      history.replaceState(null, "", window.location.pathname + "#/");
    }
  }, []);

  /* ---------- mutations ---------- */
  const allTags = useMemo(() => tags?.items.map((i) => i.tag) ?? [], [tags]);

  async function doArchive(link: LinkOut, archived: boolean) {
    try {
      await api.setArchived(link.code, archived);
      toast(archived ? `Archived /${link.code}` : `Restored /${link.code}`, archived ? "info" : "ok", archived
        ? {
            label: "Undo",
            run: async () => {
              await api.setArchived(link.code, false);
              toast(`Restored /${link.code}`, "ok");
              refresh();
            },
          }
        : undefined);
      refresh();
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }

  async function doDelete(codes: string[], bulk: boolean) {
    try {
      if (bulk) {
        const res = await api.bulkAction("delete", codes);
        toast(`Deleted ${res.updated} link${res.updated === 1 ? "" : "s"}${res.not_found ? ` · ${res.not_found} skipped` : ""}`, "info");
      } else {
        await api.deleteLink(codes[0]);
        toast(`Deleted /${codes[0]}`, "info");
      }
      setSelected(new Set());
      refresh();
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }

  async function doBulk(action: "archive" | "restore") {
    const codes = [...selected];
    try {
      const res = await api.bulkAction(action, codes);
      toast(`${action === "archive" ? "Archived" : "Restored"} ${res.updated} link${res.updated === 1 ? "" : "s"}`, "info", action === "archive"
        ? {
            label: "Undo",
            run: async () => {
              await api.bulkAction("restore", codes);
              toast("Restored", "ok");
              refresh();
            },
          }
        : undefined);
      setSelected(new Set());
      refresh();
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }

  /* ---------- derived ---------- */
  const items = useMemo(() => {
    let rows = data?.items ?? [];
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter(
        (l) =>
          l.code.toLowerCase().includes(q) ||
          l.original_url.toLowerCase().includes(q) ||
          l.tags.some((t) => t.includes(q)),
      );
    }
    if (status === "all") rows = [...rows].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return rows;
  }, [data, search, status]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / perPage)) : 1;
  const lastClick = activity?.items?.[0];
  const shown = items;
  const pageFrom = data ? data.offset + 1 : 0;
  const pageTo = data ? data.offset + (data.items?.length ?? 0) : 0;

  const visibleCodes = (data?.items ?? []).map((l) => l.code);
  const allVisibleSelected = visibleCodes.length > 0 && visibleCodes.every((c) => selected.has(c));

  /* ---------- render ---------- */
  return (
    <div className="relative mx-auto min-h-screen w-full max-w-7xl px-3 pb-28 pt-4 sm:px-5">
      {/* header */}
      <header className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-lg shadow-emerald-600/25">⚡</span>
          <div>
            <h1 className="text-lg font-extrabold leading-tight tracking-tight">Shortly</h1>
            <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <StatusDot state={health} /> {healthInfo || "checking…"}
            </p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <IconBtn label="Refresh data" onClick={refresh}>
            <I.Refresh size={16} />
          </IconBtn>
          <IconBtn label="Toggle theme" onClick={toggleTheme}>
            {theme === "dark" ? <I.Sun size={16} /> : <I.Moon size={16} />}
          </IconBtn>
          <IconBtn label="Disconnect" onClick={onDisconnect}>
            <I.Logout size={16} />
          </IconBtn>
        </div>
      </header>

      {/* stats strip */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StripCard icon={<I.Link size={14} />} label={`Links · ${status}`} value={data ? fmtInt(data.total) : "…"} />
        <StripCard icon={<I.Chart size={14} />} label="Clicks · 30d" value={devices ? fmtInt(devices.total) : "…"} accent />
        <StripCard icon={<I.Tag size={14} />} label="Tags" value={tags ? fmtInt(tags.items.length) : "…"} />
        <StripCard icon={<I.Clock size={14} />} label="Last click" value={lastClick ? relTime(lastClick.clicked_at) : "—"} sub={lastClick ? `/${lastClick.code}` : undefined} />
      </div>

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* ============ left: table ============ */}
        <section className="card">
          {/* toolbar */}
          <div className="card-pad !pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-xl bg-slate-100 p-0.5 dark:bg-slate-800/80">
                {(["active", "archived", "all"] as Status[]).map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setStatus(s);
                      setPage(0);
                      setSelected(new Set());
                    }}
                    aria-current={status === s}
                    className={cx(
                      "rounded-[10px] px-3 py-1.5 text-xs font-semibold capitalize transition-colors",
                      status === s ? "bg-white text-emerald-600 shadow-sm dark:bg-slate-950 dark:text-emerald-400" : "text-slate-500 hover:text-slate-700 dark:text-slate-400",
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <div className="relative min-w-[9rem] flex-1">
                <I.Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
                <Input
                  ref={searchRef}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter links…  ( / )"
                  className="pl-9"
                />
              </div>
              {allTags.length ? (
                <Select value={tag} onChange={(e) => { setTag(e.target.value); setPage(0); }} className="w-36">
                  <option value="">all tags</option>
                  {allTags.map((t) => (
                    <option key={t} value={t}>
                      #{t}
                    </option>
                  ))}
                </Select>
              ) : null}
              <Select value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(0); }} className="w-[4.5rem]">
                {[10, 25, 50].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
              <Button variant="primary" onClick={() => setDialogs((d) => ({ ...d, create: true }))} className="!px-3" title="Create link (n)">
                <I.Plus size={15} /> <span className="hidden sm:inline">New link</span>
              </Button>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
              {tag ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-600/10 px-2 py-0.5 font-semibold text-emerald-600 dark:text-emerald-400">
                  filtered by #{tag}
                  <button onClick={() => setTag("")} aria-label="Clear tag filter"><I.X size={11} /></button>
                </span>
              ) : null}
              <a href={api.linksCsvUrl()} className="inline-flex items-center gap-1 hover:text-emerald-500">
                <I.Download size={11} /> links CSV
              </a>
              <button onClick={() => setDialogs((d) => ({ ...d, compare: true }))} className="inline-flex items-center gap-1 hover:text-emerald-500">
                <I.Compare size={11} /> compare two links
              </button>
            </div>
          </div>

          {/* table */}
          {listErr ? (
            <div className="mx-4 mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-600 dark:text-rose-300">{listErr}</div>
          ) : null}

          {listLoading ? (
            <div className="flex justify-center py-14 text-slate-400">
              <Spinner className="h-6 w-6" />
            </div>
          ) : shown.length === 0 ? (
            <Empty
              icon="🔗"
              title={search || tag ? "No links match this filter." : status === "archived" ? "Nothing archived." : "No links yet."}
              hint={search || tag ? "Try clearing the search or tag filter." : "Create your first short link — it takes two seconds."}
            >
              {!search && !tag && status !== "archived" ? (
                <Button variant="primary" className="mt-2" onClick={() => setDialogs((d) => ({ ...d, create: true }))}>
                  <I.Plus size={15} /> Create a short link
                </Button>
              ) : null}
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="tbl w-full min-w-[720px]">
                <thead>
                  <tr>
                    <th className="w-8">
                      <input
                        type="checkbox"
                        aria-label="Select all visible"
                        checked={allVisibleSelected}
                        onChange={(e) =>
                          setSelected(e.target.checked ? new Set(visibleCodes) : new Set())
                        }
                        className="h-3.5 w-3.5 rounded accent-emerald-600"
                      />
                    </th>
                    <th>Code</th>
                    <th>Destination</th>
                    <th className="hidden md:table-cell">Tags</th>
                    <th className="hidden sm:table-cell">Created</th>
                    <th className="text-right">Clicks</th>
                    <th className="w-px text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((l) => {
                    const expired = l.expires_at ? new Date(l.expires_at).getTime() < Date.now() : false;
                    const isSel = selected.has(l.code);
                    return (
                      <tr key={l.code} className={cx(isSel && "bg-emerald-500/5", l.archived && "opacity-60")}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Select ${l.code}`}
                            checked={isSel}
                            onChange={(e) =>
                              setSelected((prev) => {
                                const next = new Set(prev);
                                if (e.target.checked) next.add(l.code);
                                else next.delete(l.code);
                                return next;
                              })
                            }
                            className="h-3.5 w-3.5 rounded accent-emerald-600"
                          />
                        </td>
                        <td>
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => setDialogs((d) => ({ ...d, stats: l.code }))}
                              className="rounded-lg bg-slate-100 px-2 py-1 font-mono text-xs font-bold text-emerald-700 transition-colors hover:bg-emerald-600 hover:text-white dark:bg-slate-800 dark:text-emerald-400 dark:hover:bg-emerald-600 dark:hover:text-white"
                              title="Open analytics"
                            >
                              /{l.code}
                            </button>
                            {l.archived ? <span title="Archived">📦</span> : null}
                            {expired && !l.archived ? <Chip className="!bg-rose-500/10 !text-rose-500" title={`expired ${relTime(l.expires_at)}`}>expired</Chip> : null}
                          </div>
                          {l.tags.length ? (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {l.tags.map((t) => (
                                <Chip key={t} hue={tagHue(t)} onClick={() => { setTag(t); setPage(0); }} title={`Filter by #${t}`}>
                                  #{t}
                                </Chip>
                              ))}
                            </div>
                          ) : null}
                        </td>
                        <td className="max-w-[16rem]">
                          <a href={l.original_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-slate-600 hover:text-emerald-600 dark:text-slate-300 dark:hover:text-emerald-400" title={l.original_url}>
                            <I.External size={12} className="shrink-0 opacity-60" />
                            <span className="truncate">
                              <span className="font-medium">{hostOf(l.original_url)}</span>
                              <span className="text-slate-400 dark:text-slate-500">{pathOf(l.original_url)}</span>
                            </span>
                          </a>
                        </td>
                        <td className="hidden md:table-cell text-slate-400">{relTime(l.created_at)}</td>
                        <td className="text-right">
                          <ClicksBadge n={l.total_clicks} />
                        </td>
                        <td>
                          <div className="flex items-center justify-end gap-0.5">
                            <IconBtn label="Copy short URL" onClick={async () => { await navigator.clipboard.writeText(l.short_url); toast("Short URL copied", "ok"); }}>
                              <I.Copy size={15} />
                            </IconBtn>
                            <IconBtn label="QR code" onClick={() => setDialogs((d) => ({ ...d, qr: l }))}>
                              <I.Qr size={15} />
                            </IconBtn>
                            <IconBtn label="Edit" onClick={() => setDialogs((d) => ({ ...d, edit: l }))}>
                              <I.Edit size={15} />
                            </IconBtn>
                            <IconBtn label={l.archived ? "Restore" : "Archive"} onClick={() => doArchive(l, !l.archived)}>
                              {l.archived ? <I.Restore size={15} /> : <I.Archive size={15} />}
                            </IconBtn>
                            <IconBtn label="Delete" className="hover:!text-rose-500" onClick={() => setConfirmDelete({ codes: [l.code], bulk: false })}>
                              <I.Trash size={15} />
                            </IconBtn>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* pagination */}
          {data && data.total > 0 ? (
            <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2.5 text-xs text-slate-400 dark:border-slate-800">
              <span className="tabular-nums">
                {pageFrom}–{pageTo} of {fmtInt(data.total)}
              </span>
              <div className="flex gap-1">
                <IconBtn label="Previous page" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} className="disabled:opacity-30">
                  <span aria-hidden>←</span>
                </IconBtn>
                <IconBtn label="Next page" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)} className="disabled:opacity-30">
                  <span aria-hidden>→</span>
                </IconBtn>
              </div>
            </div>
          ) : null}
        </section>

        {/* ============ right: panels ============ */}
        <aside className="space-y-5">
          {/* sparklines */}
          <div className="card card-pad">
            <h3 className="panel-title mb-3">Pulse · 14 days</h3>
            {spark?.items.length ? (
              <div className="grid grid-cols-2 gap-2.5">
                {spark.items.slice(0, 8).map((s) => (
                  <button
                    key={s.code}
                    onClick={() => setDialogs((d) => ({ ...d, stats: s.code }))}
                    className="rounded-xl border border-slate-100 p-2.5 text-left transition-colors hover:border-emerald-500/40 dark:border-slate-800"
                    title={`Open /${s.code} analytics`}
                  >
                    <div className="flex items-baseline justify-between gap-1">
                      <span className="truncate font-mono text-[11px] font-bold text-emerald-600 dark:text-emerald-400">/{s.code}</span>
                      <span className="text-[11px] font-bold tabular-nums">{s.total_clicks}</span>
                    </div>
                    <Sparkline points={s.points} w={132} h={30} />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">Sparklines appear once links get clicks.</p>
            )}
          </div>

          {/* devices */}
          <div className="card card-pad">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="panel-title">Devices · 30d</h3>
              <button
                onClick={() => setExcludeBots((v) => !v)}
                className={cx(
                  "rounded-full px-2 py-0.5 text-[10px] font-semibold transition-colors",
                  excludeBots ? "bg-emerald-600/10 text-emerald-600 dark:text-emerald-400" : "bg-slate-100 text-slate-400 dark:bg-slate-800",
                )}
              >
                {excludeBots ? "humans only" : "incl. bots"}
              </button>
            </div>
            {devices ? (
              <HBars items={devices.items.map((d) => ({ label: d.device, value: d.clicks, color: deviceColor(d.device) }))} />
            ) : (
              <p className="text-xs text-slate-400">Loading…</p>
            )}
          </div>

          {/* tag performance */}
          {tags && tags.items.length ? (
            <div className="card card-pad">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="panel-title">Tag performance · 30d</h3>
                <a href={api.tagCsvUrl()} className="text-[11px] text-slate-400 hover:text-emerald-500">
                  CSV
                </a>
              </div>
              <HBars items={tags.items.map((t) => ({ label: `#${t.tag}`, value: t.clicks, hue: tagHue(t.tag), sub: `${t.links} links · ${t.unique_visitors} unique` }))} />
            </div>
          ) : null}

          {/* activity */}
          <div className="card card-pad">
            <h3 className="panel-title mb-3">Live activity</h3>
            {activity?.items.length ? (
              <ul className="space-y-2">
                {activity.items.map((a, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: deviceColor(a.device) }} title={a.device} />
                    <button onClick={() => setDialogs((d) => ({ ...d, stats: a.code }))} className="font-mono font-bold text-emerald-600 hover:underline dark:text-emerald-400">
                      /{a.code}
                    </button>
                    <span className="min-w-0 flex-1 truncate text-slate-400">{a.referrer_host ?? "direct"}</span>
                    <span className="shrink-0 text-slate-300 dark:text-slate-600">{relTime(a.clicked_at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-400">No clicks yet — share a short URL to see live traffic.</p>
            )}
          </div>

          {/* sources hint */}
          <div className="card card-pad">
            <h3 className="panel-title mb-3">Top sources · 30d (first link)</h3>
            <p className="mb-2 text-[11px] text-slate-400">Per-link source × device breakdown lives in each link's analytics.</p>
            <SampleSources api={api} onOpen={(code) => setDialogs((d) => ({ ...d, stats: code }))} />
          </div>
        </aside>
      </div>

      {/* ============ bulk bar ============ */}
      {selected.size > 0 ? (
        <div className="fade-up fixed bottom-4 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-2xl border border-slate-200 bg-white/95 px-3 py-2 shadow-xl backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <span className="px-1 text-xs font-bold tabular-nums">{selected.size} selected</span>
          <Button variant="subtle" className="!py-1.5 text-xs" onClick={() => doBulk("archive")}>
            <I.Archive size={13} /> Archive
          </Button>
          <Button variant="subtle" className="!py-1.5 text-xs" onClick={() => doBulk("restore")}>
            <I.Restore size={13} /> Restore
          </Button>
          <Button variant="danger" className="!py-1.5 text-xs" onClick={() => setConfirmDelete({ codes: [...selected], bulk: true })}>
            <I.Trash size={13} /> Delete
          </Button>
          <IconBtn label="Clear selection" onClick={() => setSelected(new Set())}>
            <I.X size={14} />
          </IconBtn>
        </div>
      ) : null}

      {/* ============ delete confirm ============ */}
      {confirmDelete ? (
        <Modal open onClose={() => setConfirmDelete(null)} title={confirmDelete.bulk ? `Delete ${confirmDelete.codes.length} links?` : `Delete /${confirmDelete.codes[0]}?`}>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            This permanently removes the link{confirmDelete.bulk ? "s" : ""} and its click history. Consider <strong>Archive</strong> instead to keep stats.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={async () => {
                const c = confirmDelete;
                setConfirmDelete(null);
                await doDelete(c.codes, c.bulk);
              }}
            >
              <I.Trash size={14} /> Delete permanently
            </Button>
          </div>
        </Modal>
      ) : null}

      {/* ============ dialogs ============ */}
      {dialogs.create ? (
        <LinkFormDialog api={api} edit={null} knownTags={allTags} onClose={() => setDialogs((d) => ({ ...d, create: false }))} onSaved={() => refresh()} />
      ) : null}
      {dialogs.edit ? (
        <LinkFormDialog api={api} edit={dialogs.edit} knownTags={allTags} onClose={() => setDialogs((d) => ({ ...d, edit: null }))} onSaved={() => refresh()} />
      ) : null}
      {dialogs.stats ? (
        <StatsModal api={api} code={dialogs.stats} onClose={() => setDialogs((d) => ({ ...d, stats: null }))} onQr={(l) => setDialogs((d) => ({ ...d, stats: null, qr: l }))} />
      ) : null}
      {dialogs.qr ? <QrDialog api={api} link={dialogs.qr} onClose={() => setDialogs((d) => ({ ...d, qr: null }))} /> : null}
      {dialogs.compare ? (
        <CompareDialog api={api} codes={visibleCodes.length >= 2 ? visibleCodes : allTags.length ? visibleCodes : []} onClose={() => setDialogs((d) => ({ ...d, compare: false }))} />
      ) : null}
    </div>
  );
}

function StripCard({ icon, label, value, sub, accent }: { icon: ReactNode; label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className={cx("card card-pad !p-3.5", accent && "border-emerald-500/30 bg-emerald-500/[0.04] dark:border-emerald-500/20")}>
      <p className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400">
        <span className="text-emerald-500">{icon}</span>
        {label}
      </p>
      <p className="mt-0.5 truncate text-xl font-extrabold tabular-nums">{value}</p>
      {sub ? <p className="truncate text-[10px] text-slate-400">{sub}</p> : null}
    </div>
  );
}

/** Sample stacked-sources panel for the most recently created link with clicks. */
function SampleSources({ api, onOpen }: { api: Api; onOpen: (code: string) => void }) {
  const [state, setState] = useState<{ code: string; items: { source: string; clicks: number; devices: Record<string, number> }[] } | null>(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const spark = await api.sparklines(30, 20);
        const withClicks = spark.items.find((s) => s.total_clicks > 0);
        if (!withClicks) return;
        const detail = await api.linkDetail(withClicks.code);
        if (!alive) return;
        setState({ code: detail.code, items: detail.top_referrers.slice(0, 5) });
      } catch {
        /* panel is best-effort */
      }
    })();
    return () => {
      alive = false;
    };
  }, [api]);
  if (!state || state.items.length === 0) return <p className="text-xs text-slate-400">Sources appear once links receive traffic.</p>;
  return (
    <div>
      <button onClick={() => onOpen(state.code)} className="mb-2 font-mono text-[11px] font-bold text-emerald-600 hover:underline dark:text-emerald-400">
        /{state.code} → full analytics
      </button>
      <StackedSources items={state.items} />
    </div>
  );
}
