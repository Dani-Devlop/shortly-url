/** Hand-rolled SVG charts — no chart library, tiny and crisp. */
import { useMemo } from "react";
import type { ReferrerStat } from "./types";
import { fmtInt } from "./store";
import { cx } from "./ui";

export const DEVICE_COLORS: Record<string, string> = {
  desktop: "#10b981", // emerald
  mobile: "#8b5cf6", // violet
  tablet: "#f59e0b", // amber
  bot: "#64748b", // slate
  other: "#f43f5e", // rose
};

export const deviceColor = (d: string) => DEVICE_COLORS[d] ?? "#94a3b8";

/* ---------------- sparkline ---------------- */

export function Sparkline({
  points,
  w = 120,
  h = 34,
  color = "#10b981",
}: {
  points: number[];
  w?: number;
  h?: number;
  color?: string;
}) {
  const { line, area } = useMemo(() => {
    const max = Math.max(1, ...points);
    const n = points.length;
    const px = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * (w - 2) + 1);
    const py = (v: number) => h - 2 - (v / max) * (h - 6);
    const pts = points.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`);
    const line = pts.join(" ");
    const area = `M1,${h - 1} L${line.replace(/ /g, " L")} L${w - 1},${h - 1} Z`;
    return { line, area };
  }, [points, w, h]);
  const id = useMemo(() => `sg${Math.random().toString(36).slice(2, 8)}`, []);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="overflow-visible">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* ---------------- area chart (daily) ---------------- */

export function AreaChart({
  points,
  labels,
  h = 170,
  color = "#10b981",
}: {
  points: number[];
  labels?: string[];
  h?: number;
  color?: string;
}) {
  const W = 600;
  const H = h;
  const padB = 22;
  const max = Math.max(1, ...points);
  const niceMax = Math.ceil(max / 4) * 4 || 4;
  const n = points.length || 1;
  const px = (i: number) => 6 + (i / Math.max(1, n - 1)) * (W - 12);
  const py = (v: number) => H - padB - (v / niceMax) * (H - padB - 8);
  const line = points.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const area = `M6,${H - padB} L${line.replace(/ /g, " L")} L${W - 6},${H - padB} Z`;
  const id = useMemo(() => `ag${Math.random().toString(36).slice(2, 8)}`, []);
  const gridVals = [0, niceMax / 2, niceMax];
  const lastIdx = points.length - 1;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: h }} preserveAspectRatio="none" aria-hidden>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {gridVals.map((g) => (
          <line key={g} x1="6" x2={W - 6} y1={py(g)} y2={py(g)} className="stroke-slate-200 dark:stroke-slate-800" strokeWidth="1" />
        ))}
        {points.map((v, i) =>
          v > 0 ? (
            <rect key={i} x={px(i) - Math.max(1.5, (W - 12) / n / 2.6)} y={py(v)} width={Math.max(3, (W - 12) / n / 1.3)} height={H - padB - py(v)} rx="2" fill={color} opacity="0.14" />
          ) : null,
        )}
        <path d={area} fill={`url(#${id})`} />
        <polyline points={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
        {points.length > 0 && (
          <circle cx={px(lastIdx)} cy={py(points[lastIdx])} r="3.5" fill={color} vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-400">
        <span>{labels?.[0] ?? ""}</span>
        <span>{labels?.[Math.floor((labels?.length ?? 0) / 2)] ?? ""}</span>
        <span>{labels?.[lastIdx] ?? ""}</span>
      </div>
    </div>
  );
}

/* ---------------- dual line (compare) ---------------- */

export function DualChart({ a, b, labels, h = 180 }: { a: number[]; b: number[]; labels?: string[]; h?: number }) {
  const W = 600;
  const H = h;
  const padB = 22;
  const max = Math.max(1, ...a, ...b);
  const niceMax = Math.ceil(max / 4) * 4 || 4;
  const n = Math.max(a.length, b.length, 1);
  const px = (i: number) => 6 + (i / Math.max(1, n - 1)) * (W - 12);
  const py = (v: number) => H - padB - (v / niceMax) * (H - padB - 8);
  const poly = (pts: number[], color: string) => (
    <polyline
      points={pts.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ")}
      fill="none"
      stroke={color}
      strokeWidth="2"
      vectorEffect="non-scaling-stroke"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  );
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: h }} preserveAspectRatio="none" aria-hidden>
        {[0, niceMax / 2, niceMax].map((g) => (
          <line key={g} x1="6" x2={W - 6} y1={py(g)} y2={py(g)} className="stroke-slate-200 dark:stroke-slate-800" strokeWidth="1" />
        ))}
        {poly(a, "#10b981")}
        {poly(b, "#8b5cf6")}
      </svg>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-400">
        <span>{labels?.[0] ?? ""}</span>
        <span>{labels?.[n - 1] ?? ""}</span>
      </div>
    </div>
  );
}

/* ---------------- horizontal bars ---------------- */

export function HBars({
  items,
  unit = "clicks",
  showPct = true,
}: {
  items: { label: string; value: number; color?: string; hue?: number; sub?: string }[];
  unit?: string;
  showPct?: boolean;
}) {
  const total = items.reduce((s, i) => s + i.value, 0) || 1;
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="space-y-2.5">
      {items.map((it) => (
        <div key={it.label}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
            <span className="min-w-0 truncate font-medium text-slate-700 dark:text-slate-200">{it.label}</span>
            <span className="shrink-0 tabular-nums text-slate-400">
              {fmtInt(it.value)}
              {showPct ? <span className="ml-1 text-slate-300 dark:text-slate-600">· {Math.round((it.value / total) * 100)}%</span> : null}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200/70 dark:bg-slate-800">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.max(it.value > 0 ? 2.5 : 0, (it.value / max) * 100)}%`,
                background: it.hue !== undefined
                  ? `linear-gradient(90deg, hsl(${it.hue} 70% 45%), hsl(${it.hue} 75% 58%))`
                  : (it.color ?? "#10b981"),
              }}
            />
          </div>
          {it.sub ? <div className="mt-0.5 text-[10px] text-slate-400">{it.sub}</div> : null}
        </div>
      ))}
      {items.length === 0 ? <p className="py-2 text-center text-xs text-slate-400">No {unit} yet.</p> : null}
    </div>
  );
}

/* ---------------- stacked sources (referrer × device) ---------------- */

export function StackedSources({ items }: { items: ReferrerStat[] }) {
  const max = Math.max(1, ...items.map((i) => i.clicks));
  const devices = Array.from(new Set(items.flatMap((i) => Object.keys(i.devices))));
  return (
    <div className="space-y-2.5">
      {items.map((it) => (
        <div key={it.source}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
            <span className="min-w-0 truncate font-medium text-slate-700 dark:text-slate-200">{it.source}</span>
            <span className="shrink-0 tabular-nums text-slate-400">{fmtInt(it.clicks)}</span>
          </div>
          <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-slate-800">
            {Object.entries(it.devices).map(([dev, n]) => (
              <div
                key={dev}
                title={`${dev}: ${n}`}
                style={{
                  width: `${(n / max) * 100}%`,
                  minWidth: n > 0 ? 2 : 0,
                  background: deviceColor(dev),
                }}
                className="h-full"
              />
            ))}
          </div>
        </div>
      ))}
      {items.length === 0 ? <p className="py-2 text-center text-xs text-slate-400">No referrer data in this window.</p> : null}
      {items.length > 0 && devices.length > 1 ? (
        <div className="flex flex-wrap gap-3 pt-1">
          {devices.map((d) => (
            <span key={d} className="inline-flex items-center gap-1.5 text-[10px] text-slate-400">
              <span className="h-2 w-2 rounded-full" style={{ background: deviceColor(d) }} />
              {d}
            </span>
          ))}
          <span className="ml-auto text-[10px] text-slate-300 dark:text-slate-600">segments = device mix</span>
        </div>
      ) : null}
    </div>
  );
}

/* ---------------- click-hour heatmap ---------------- */

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function Heatmap({ cells, peak }: { cells: { dow: number; hour: number; clicks: number }[]; peak: number }) {
  const grid = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of cells) m.set(`${c.dow}:${c.hour}`, c.clicks);
    return m;
  }, [cells]);
  const max = Math.max(1, peak);
  return (
    <div className="overflow-x-auto">
      <div className="inline-block min-w-[430px]">
        <div className="mb-1 flex gap-[2px] pl-9 text-[9px] tabular-nums text-slate-400">
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className="w-[15px] text-center">
              {h % 6 === 0 ? h : ""}
            </span>
          ))}
        </div>
        {DOW.map((d, dow) => (
          <div key={d} className="mb-[2px] flex items-center gap-[2px]">
            <span className="w-9 shrink-0 text-[9px] text-slate-400">{d}</span>
            {Array.from({ length: 24 }, (_, hour) => {
              const v = grid.get(`${dow}:${hour}`) ?? 0;
              const a = v === 0 ? 0 : 0.18 + (v / max) * 0.82;
              return (
                <div
                  key={hour}
                  title={`${d} ${String(hour).padStart(2, "0")}:00 — ${v} clicks`}
                  className={cx("h-[15px] w-[15px] rounded-[3px]", v === 0 && "bg-slate-200/70 dark:bg-slate-800/80")}
                  style={v > 0 ? { background: `rgb(16 185 129 / ${a.toFixed(2)})` } : undefined}
                />
              );
            })}
          </div>
        ))}
        <div className="mt-2 flex items-center gap-1.5 pl-9 text-[10px] text-slate-400">
          <span>less</span>
          {[0.12, 0.35, 0.6, 0.85, 1].map((a) => (
            <span key={a} className="h-[10px] w-[10px] rounded-[3px]" style={{ background: `rgb(16 185 129 / ${a})` }} />
          ))}
          <span>busy</span>
        </div>
      </div>
    </div>
  );
}
