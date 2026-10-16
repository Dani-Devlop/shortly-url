/** Minimal design system: buttons, inputs, modal, chips, icons. */
import { forwardRef } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useEffect } from "react";
import { useStore } from "./store";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

/* ================= buttons ================= */

type BtnVariant = "primary" | "ghost" | "subtle" | "danger" | "outline";

export function Button({
  variant = "subtle",
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  const styles: Record<BtnVariant, string> = {
    primary:
      "bg-emerald-600 text-white hover:bg-emerald-500 shadow-sm shadow-emerald-600/20 disabled:bg-emerald-600/50",
    ghost:
      "text-slate-600 hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800",
    subtle:
      "bg-slate-200/70 text-slate-700 hover:bg-slate-300/70 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700",
    danger:
      "bg-rose-600/10 text-rose-600 hover:bg-rose-600/20 dark:text-rose-400 dark:bg-rose-500/10 dark:hover:bg-rose-500/20",
    outline:
      "border border-slate-300 text-slate-700 hover:border-emerald-500 hover:text-emerald-600 dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-500 dark:hover:text-emerald-400",
  };
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        styles[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function IconBtn({
  label,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      title={label}
      aria-label={label}
      className={cx(
        "inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-100",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ================= form controls ================= */

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(props, ref) {
  return <input ref={ref} {...props} className={cx("inp", props.className)} />;
});

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cx(
        "inp cursor-pointer appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2394a3b8%22 stroke-width=%222.4%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[right_0.6rem_center] bg-no-repeat pr-8",
        props.className,
      )}
    />
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="lbl">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-slate-400">{hint}</span> : null}
    </label>
  );
}

/* ================= chips & badges ================= */

export function Chip({
  children,
  hue,
  className,
  onClick,
  title,
}: {
  children: ReactNode;
  hue?: number;
  className?: string;
  onClick?: () => void;
  title?: string;
}) {
  const style =
    hue === undefined
      ? undefined
      : {
          backgroundColor: `hsl(${hue} 70% 50% / 0.14)`,
          color: `hsl(${hue} 65% 42%)`,
        };
  const Comp = onClick ? "button" : "span";
  return (
    <Comp
      title={title}
      onClick={onClick}
      style={style}
      className={cx(
        "inline-flex max-w-[10rem] items-center truncate rounded-full px-2 py-0.5 text-[11px] font-semibold",
        hue === undefined && "bg-slate-200/80 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
        onClick && "transition-transform hover:scale-105",
        className,
      )}
    >
      {children}
    </Comp>
  );
}

export function ClicksBadge({ n }: { n: number }) {
  return (
    <span
      className={cx(
        "inline-flex min-w-[2.2rem] justify-center rounded-lg px-1.5 py-0.5 text-xs font-bold tabular-nums",
        n === 0
          ? "bg-slate-200/70 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
          : "bg-emerald-600/10 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400",
      )}
    >
      {n.toLocaleString("en-US")}
    </span>
  );
}

export function StatusDot({ state }: { state: "ok" | "bad" | "unknown" }) {
  const color =
    state === "ok" ? "bg-emerald-500" : state === "bad" ? "bg-rose-500" : "bg-slate-400";
  return (
    <span className="relative inline-flex h-2 w-2">
      {state === "ok" && (
        <span className={cx("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", color)} />
      )}
      <span className={cx("relative inline-flex h-2 w-2 rounded-full", color)} />
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("h-4 w-4 animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" className="opacity-25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Empty({ icon, title, hint, children }: { icon?: ReactNode; title: string; hint?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl px-6 py-10 text-center">
      {icon ? <div className="text-3xl opacity-70">{icon}</div> : null}
      <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">{title}</p>
      {hint ? <p className="max-w-sm text-xs text-slate-400">{hint}</p> : null}
      {children}
    </div>
  );
}

/* ================= modal ================= */

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  wide,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6" role="dialog" aria-modal>
      <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div
        className={cx(
          "pop-in relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900 sm:rounded-2xl",
          wide ? "sm:max-w-3xl" : "sm:max-w-lg",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div className="min-w-0">
            <h2 className="truncate text-base font-bold">{title}</h2>
            {subtitle ? <div className="mt-0.5 truncate text-xs text-slate-400">{subtitle}</div> : null}
          </div>
          <IconBtn label="Close" onClick={onClose}>
            <I.X />
          </IconBtn>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

/* ================= toasts ================= */

export function Toasts() {
  const { toasts, dismiss } = useStore();
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-[70] flex w-full max-w-sm -translate-x-1/2 flex-col gap-2 px-3">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cx(
            "fade-up pointer-events-auto flex items-center gap-2 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur",
            t.kind === "ok" && "border-emerald-500/30 bg-emerald-50/95 text-emerald-800 dark:bg-emerald-950/90 dark:text-emerald-200",
            t.kind === "err" && "border-rose-500/30 bg-rose-50/95 text-rose-800 dark:bg-rose-950/90 dark:text-rose-200",
            t.kind === "info" && "border-slate-300/50 bg-white/95 text-slate-700 dark:bg-slate-900/95 dark:text-slate-200",
          )}
          role="status"
        >
          <span className="shrink-0">{t.kind === "ok" ? <I.Check /> : t.kind === "err" ? <I.Alert /> : <I.Bolt />}</span>
          <span className="min-w-0 flex-1">{t.text}</span>
          {t.action ? (
            <button
              className="shrink-0 rounded-lg bg-slate-900/10 px-2 py-1 text-xs font-bold uppercase tracking-wide hover:bg-slate-900/20 dark:bg-white/10 dark:hover:bg-white/20"
              onClick={async () => {
                dismiss(t.id);
                await t.action!.run();
              }}
            >
              {t.action.label}
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/* ================= icons (inline, stroke) ================= */

const svg = (path: ReactNode) =>
  function IconSvg({ className, size = 16 }: { className?: string; size?: number }) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden
      >
        {path}
      </svg>
    );
  };

export const I = {
  Plus: svg(<path d="M12 5v14M5 12h14" />),
  Search: svg(<circle cx="11" cy="11" r="7" />),
  X: svg(<path d="M18 6 6 18M6 6l12 12" />),
  Copy: svg(
    <>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </>,
  ),
  External: svg(
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4 10 14" />
      <path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" />
    </>,
  ),
  Edit: svg(
    <>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </>,
  ),
  Trash: svg(
    <>
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
    </>,
  ),
  Archive: svg(
    <>
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8" />
      <path d="M10 12h4" />
    </>,
  ),
  Restore: svg(
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5" />
    </>,
  ),
  Qr: svg(
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <path d="M14 14h3v3h-3zM19 19h2v2h-2z" />
    </>,
  ),
  Chart: svg(<path d="M3 3v18h18M7 15v3M12 10v8M17 6v12" />),
  Sun: svg(
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>,
  ),
  Moon: svg(<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />),
  Undo: svg(
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5" />
    </>,
  ),
  Tag: svg(
    <>
      <path d="M12 2H2v10l9.3 9.3a1 1 0 0 0 1.4 0l8.6-8.6a1 1 0 0 0 0-1.4Z" />
      <circle cx="7.5" cy="7.5" r="1" />
    </>,
  ),
  Compare: svg(<path d="M3 17l6-6 4 4 8-8M15 7h6v6" />),
  Refresh: svg(
    <>
      <path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" />
      <path d="M21 3v5h-5" />
    </>,
  ),
  Logout: svg(
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </>,
  ),
  Check: svg(<path d="m4 12.5 5 5L20 6.5" />),
  Alert: svg(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" />
    </>,
  ),
  Bolt: svg(<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />),
  Download: svg(
    <>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </>,
  ),
  Key: svg(
    <>
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="m11 12 9-9M17 6l3 3" />
    </>,
  ),
  Link: svg(
    <>
      <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" />
      <path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />
    </>,
  ),
  Eye: svg(
    <>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </>,
  ),
  Clock: svg(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>,
  ),
};
