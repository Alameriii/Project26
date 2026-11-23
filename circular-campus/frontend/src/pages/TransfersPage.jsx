import { useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorState, LoadingRows, Status } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDate } from "../lib/format.js";
import { useAsync } from "../lib/useAsync.js";

export default function TransfersPage() {
  const [scope, setScope] = useState("action");
  const { data, error, loading, reload } = useAsync(() => api.get("/transfers", { scope }), [scope]);
  const items = data?.items || [];
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Transfers</h1>
          <p>Approved moves between departments. The sender marks the item dispatched; the receiver confirms it arrived.</p>
        </div>
      </div>
      <div className="segmented" role="group" aria-label="Filter transfers" style={{ marginBottom: 16 }}>
        <button aria-pressed={scope === "action"} onClick={() => setScope("action")}>Needs my action</button>
        <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>All I can see</button>
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      <div className="panel">
        {loading && !data ? <LoadingRows /> : items.length === 0 ? (
          <Empty title={scope === "action" ? "Nothing to dispatch or receive" : "No transfers yet"}>
            {scope === "action"
              ? "When a request is approved, the sending and receiving sides see the transfer here."
              : "Transfers you are involved in, or that touch your department, will be listed here."}
          </Empty>
        ) : (
          <ul className="list">
            {items.map((t) => (
              <li key={t.id}>
                <Link to={`/transfers/${t.id}`} className="row">
                  <div style={{ minWidth: 0 }}>
                    <div className="row-title">{t.quantity} × {t.asset.name}</div>
                    <div className="row-meta">
                      <span className="num">{t.transfer_code}</span>, {t.from_department.name} to {t.to_department.name}
                    </div>
                  </div>
                  <div className="row-side">
                    <span>{t.method}, {fmtDate(t.scheduled_date)}</span>
                    <Status value={t.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
