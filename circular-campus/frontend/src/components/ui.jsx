import { useEffect, useId, useRef } from "react";
import { fmtDateTime, statusTone } from "../lib/format.js";

/* ---------- icons (simple strokes, 18px) ---------- */
const paths = {
  search: <><circle cx="8" cy="8" r="5.5" /><path d="M12.2 12.2 16 16" /></>,
  bell: <><path d="M5 7.5a4 4 0 0 1 8 0c0 4 1.5 5 1.5 5h-11S5 11.5 5 7.5Z" /><path d="M7.6 15a1.6 1.6 0 0 0 2.8 0" /></>,
  sparkle: <><path d="M9 2.5 10.4 7.6 15.5 9 10.4 10.4 9 15.5 7.6 10.4 2.5 9 7.6 7.6Z" /></>,
  info: <><circle cx="9" cy="9" r="6.8" /><path d="M9 8.2v4.2M9 5.8v.1" /></>,
  alert: <><path d="M9 2.8 16 15H2Z" /><path d="M9 7.5v3.3M9 12.8v.1" /></>,
  check: <><path d="m3.5 9.5 3.5 3.5 7.5-8" /></>,
  box: <><path d="M2.8 5.5 9 2.5l6.2 3v7L9 15.5l-6.2-3Z" /><path d="M2.8 5.5 9 8.5l6.2-3M9 8.5v7" /></>,
  chair: <><path d="M5 9.5V3.5h8v6M4 9.5h10v2H4ZM5 11.5v4M13 11.5v4" /></>,
  screen: <><rect x="2.5" y="3" width="13" height="9" rx="1.5" /><path d="M6.5 15.5h5M9 12v3.5" /></>,
  flask: <><path d="M7 2.5h4M7.5 2.5v5L3.5 14a1 1 0 0 0 .9 1.5h9.2a1 1 0 0 0 .9-1.5l-4-6.5v-5" /></>,
  book: <><path d="M3 3.5h4.5A1.5 1.5 0 0 1 9 5v10a1.5 1.5 0 0 0-1.5-1.5H3ZM15 3.5h-4.5A1.5 1.5 0 0 0 9 5v10a1.5 1.5 0 0 1 1.5-1.5H15Z" /></>,
  projector: <><rect x="2.5" y="6" width="13" height="6.5" rx="1.5" /><circle cx="11.5" cy="9.25" r="1.7" /><path d="M4.5 12.5v2M13.5 12.5v2" /></>,
  phone: <><path d="M4 2.5h3l1.2 3.2-1.7 1a8 8 0 0 0 4.8 4.8l1-1.7 3.2 1.2v3a1.5 1.5 0 0 1-1.6 1.5A12.5 12.5 0 0 1 2.5 4.1 1.5 1.5 0 0 1 4 2.5Z" /></>,
  plus: <><path d="M9 3.5v11M3.5 9h11" /></>,
  close: <><path d="m4.5 4.5 9 9M13.5 4.5l-9 9" /></>,
  truck: <><path d="M1.8 4.5h9v7.5h-9ZM10.8 7.5h3l2.4 2.6V12h-5.4" /><circle cx="5" cy="13" r="1.6" /><circle cx="13" cy="13" r="1.6" /></>,
  out: <><path d="M7 3H3.5v12H7M11.5 12.5 15 9l-3.5-3.5M15 9H7" /></>,
};

export function Icon({ name, size = 18, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {paths[name]}
    </svg>
  );
}

const CATEGORY_ICON = {
  "IT Equipment": "screen",
  "Audio-Visual": "projector",
  Furniture: "chair",
  "Laboratory Equipment": "flask",
  "Books & Learning Materials": "book",
  "Office Equipment": "phone",
};

export function CategoryGlyph({ category }) {
  return (
    <span className="cat-glyph" aria-hidden="true">
      <Icon name={CATEGORY_ICON[category] || "box"} size={20} />
    </span>
  );
}

export function Logo({ size = 22 }) {
  // An open loop closing on itself: reuse, not disposal.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M19.5 12a7.5 7.5 0 1 1-3-6" stroke="#2E6A56" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M17.2 2.8l-.6 3.4 3.4.4" stroke="#2E6A56" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="2.6" fill="#2E6A56" />
    </svg>
  );
}

/* ---------- small pieces ---------- */
export function Status({ value }) {
  if (!value) return null;
  return <span className={`status ${statusTone(value)}`}>{value}</span>;
}

export function Notice({ tone = "info", children, icon }) {
  const ic = icon || (tone === "error" || tone === "warn" ? "alert" : tone === "success" ? "check" : "info");
  return (
    <div className={`notice ${tone}`} role={tone === "error" ? "alert" : undefined}>
      <Icon name={ic} size={16} />
      <div>{children}</div>
    </div>
  );
}

export function Button({ loading, children, variant = "secondary", size, className = "", ...rest }) {
  return (
    <button className={`btn btn-${variant} ${size === "sm" ? "btn-sm" : ""} ${className}`}
      disabled={loading || rest.disabled} {...rest}>
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function Field({ label, error, hint, optional, children, className = "", id }) {
  const autoId = useId();
  const fid = id || autoId;
  const child = typeof children === "function" ? children({ id: fid, invalid: !!error,
    "aria-invalid": !!error || undefined, "aria-describedby": error ? `${fid}-err` : hint ? `${fid}-hint` : undefined })
    : children;
  return (
    <div className={`field ${className}`}>
      {label && (
        <label htmlFor={fid}>
          {label} {optional && <span className="optional">(optional)</span>}
        </label>
      )}
      {child}
      {error ? <div className="error" id={`${fid}-err`}>{error}</div>
        : hint ? <div className="hint" id={`${fid}-hint`}>{hint}</div> : null}
    </div>
  );
}

export function Input({ invalid, className = "", ...rest }) {
  return <input className={`input ${invalid ? "invalid" : ""} ${className}`} {...rest} />;
}

export function Select({ invalid, className = "", children, ...rest }) {
  return (
    <select className={`input ${invalid ? "invalid" : ""} ${className}`} {...rest}>
      {children}
    </select>
  );
}

export function Textarea({ invalid, className = "", ...rest }) {
  return <textarea className={`input ${invalid ? "invalid" : ""} ${className}`} {...rest} />;
}

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function LoadingRows({ rows = 4 }) {
  return (
    <div className="loading-rows" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ width: `${70 - i * 9}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="panel panel-pad">
      <Notice tone="error">
        {error?.message || "Something went wrong."}{" "}
        {onRetry && (
          <button className="btn btn-quiet btn-sm" onClick={onRetry}>Try again</button>
        )}
      </Notice>
    </div>
  );
}

export function Modal({ title, description, onClose, children, labelledBy }) {
  const ref = useRef(null);
  const titleId = useId();
  useEffect(() => {
    const prev = document.activeElement;
    const el = ref.current;
    const first = el?.querySelector("input, select, textarea, button");
    first?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && el) {
        const items = [...el.querySelectorAll("input, select, textarea, button, a[href]")].filter((x) => !x.disabled);
        if (!items.length) return;
        const firstEl = items[0];
        const lastEl = items[items.length - 1];
        if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
        else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={labelledBy || titleId} ref={ref}>
        <h2 id={titleId}>{title}</h2>
        {description && <p className="muted" style={{ marginBottom: 18 }}>{description}</p>}
        {children}
      </div>
    </div>
  );
}

export function ScoreLoop({ score, size = 56 }) {
  const pct = Math.round(score * 100);
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const tone = pct >= 75 ? "" : pct >= 55 ? "mid" : "weak";
  return (
    <div className={`loop ${tone}`} style={{ width: size, height: size }} role="img"
      aria-label={`Match score ${pct} out of 100`}>
      <svg width={size} height={size}>
        <circle className="track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="5" />
        <circle className="arc" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="5" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - score)} />
      </svg>
      <span className="loop-num">{pct}</span>
    </div>
  );
}

export function Confidence({ value, low }) {
  if (value === null || value === undefined) return null;
  return (
    <span className={`conf ${low ? "low" : ""}`}>
      {low ? "Low confidence – review carefully" : `Confidence ${value.toFixed(2)}`}
    </span>
  );
}

function describeChanges(details) {
  const changes = details?.changes;
  if (!changes || typeof changes !== "object") return null;
  const parts = Object.entries(changes).map(([k, v]) => {
    const label = k.replace(/_/g, " ");
    const show = (x) => (Array.isArray(x) ? x.join(", ") : x === null || x === "" ? "—" : String(x));
    return `${label}: ${show(v.old)} → ${show(v.new)}`;
  });
  return parts.join("; ");
}

export function Timeline({ items }) {
  if (!items?.length) return <p className="muted">No history yet.</p>;
  return (
    <ol className="timeline">
      {items.map((e) => {
        const changes = describeChanges(e.details);
        const note = e.details?.note || e.details?.reason;
        return (
          <li key={e.id}>
            <div className="when">
              {fmtDateTime(e.at)}, by {e.user ? e.user.name : "the system"}
            </div>
            <div className="what">
              {e.action}
              {e.to_status && e.from_status !== e.to_status && (
                <span className="faint" style={{ fontWeight: 400 }}>
                  {" "}({e.from_status ? `${e.from_status} → ` : ""}{e.to_status})
                </span>
              )}
            </div>
            <div className="muted small">{e.summary}</div>
            {changes && <div className="changes">{changes}</div>}
            {note && <div className="changes">Note: {note}</div>}
          </li>
        );
      })}
    </ol>
  );
}
