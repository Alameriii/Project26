import { useState } from "react";
import { Link } from "react-router-dom";
import { FACTOR_LABELS } from "../lib/format.js";
import { Confidence, Notice, ScoreLoop } from "./ui.jsx";

const EXCLUDE_LABELS = {
  "not available": "not available",
  "your own department": "already in your department",
  "quantity too low": "not enough units",
  "condition below minimum": "below your minimum condition",
  "listing ended": "listing ended",
  "low relevance": "not relevant enough",
};

export function MatchSource({ result }) {
  if (!result) return null;
  return (
    <div style={{ marginBottom: 14 }}>
      {result.notice ? (
        <Notice tone={result.provider === "gemini" ? "info" : "warn"}>{result.notice}</Notice>
      ) : (
        <Notice tone="info">Ranked with {result.model_version}.</Notice>
      )}
    </div>
  );
}

export function ExcludedSummary({ excluded, considered }) {
  const parts = Object.entries(excluded || {}).map(([k, n]) => `${n} ${EXCLUDE_LABELS[k] || k}`);
  if (!parts.length) return null;
  return (
    <p className="faint small" style={{ marginTop: 12 }}>
      Checked {considered + Object.values(excluded).reduce((a, b) => a + b, 0) - (excluded["low relevance"] || 0)} available items.
      Left out: {parts.join(", ")}.
    </p>
  );
}

export default function MatchList({ matches, selected, onSelect }) {
  const [openId, setOpenId] = useState(null);
  return (
    <div className="matches" role="radiogroup" aria-label="Suggested matches">
      {matches.map((m) => {
        const a = m.asset;
        const isSel = selected === a.id;
        return (
          <label key={a.id} className={`match ${isSel ? "selected" : ""}`}>
            <input type="radio" name="match" value={a.id} checked={isSel} onChange={() => onSelect(a.id)} />
            <ScoreLoop score={m.score} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 500 }}>
                {a.name} <span className="faint small num">{a.asset_code}</span>
              </div>
              <div className="row-meta">
                {a.department.name}, {a.campus}, {a.quantity} {a.quantity === 1 ? "unit" : "units"}, {a.condition}
              </div>
              <p className="reason">{m.reason}</p>
              {openId === a.id && (
                <dl className="facts small" style={{ gridTemplateColumns: "140px auto", marginTop: 10, gap: "4px 14px" }}>
                  {Object.entries(FACTOR_LABELS).map(([k, label]) => (
                    <FactorRow key={k} label={label} value={m.factors[k]} />
                  ))}
                </dl>
              )}
            </div>
            <div className="match-side" style={{ textAlign: "right", display: "grid", gap: 6, justifyItems: "end" }}>
              <Confidence value={m.confidence} low={m.low_confidence} />
              <button type="button" className="btn btn-quiet btn-sm"
                onClick={(e) => { e.preventDefault(); setOpenId(openId === a.id ? null : a.id); }}>
                {openId === a.id ? "Hide factors" : "Show factors"}
              </button>
              <Link to={`/assets/${a.id}`} className="small" target="_blank" rel="noreferrer"
                onClick={(e) => e.stopPropagation()}>Open item</Link>
            </div>
          </label>
        );
      })}
    </div>
  );
}

function FactorRow({ label, value }) {
  return (
    <>
      <dt>{label}</dt>
      <dd style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span aria-hidden="true" style={{ display: "inline-block", width: 80, height: 5, borderRadius: 3, background: "var(--grey-tint)", position: "relative", overflow: "hidden" }}>
          <span style={{ position: "absolute", inset: 0, width: `${Math.round(value * 100)}%`, background: "var(--accent)", borderRadius: 3 }} />
        </span>
        <span className="num">{value.toFixed(2)}</span>
      </dd>
    </>
  );
}
