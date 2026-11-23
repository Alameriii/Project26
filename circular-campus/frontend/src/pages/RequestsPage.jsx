import { useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorState, LoadingRows, Status } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDate, relative } from "../lib/format.js";
import { useSession } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

const GROUPS = {
  active: ["Open", "Submitted", "Under Review", "Approved"],
  closed: ["Fulfilled", "Rejected", "Cancelled", "Expired"],
};

export default function RequestsPage() {
  const { user } = useSession();
  const [tab, setTab] = useState("active");
  const { data, error, loading, reload } = useAsync(() => api.get("/requests", { scope: "mine" }), []);
  const items = (data?.items || []).filter((r) => GROUPS[tab].includes(r.status));

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>My requests</h1>
          <p>Track what you have asked for. A request holds its item for 3 working days while the owner decides.</p>
        </div>
        {user.can.submit_requests && <Link className="btn btn-primary" to="/requests/new">New request</Link>}
      </div>
      <div className="segmented" role="group" aria-label="Filter requests" style={{ marginBottom: 16 }}>
        <button aria-pressed={tab === "active"} onClick={() => setTab("active")}>Active</button>
        <button aria-pressed={tab === "closed"} onClick={() => setTab("closed")}>Closed</button>
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      <div className="panel">
        {loading && !data ? <LoadingRows /> : items.length === 0 ? (
          <Empty title={tab === "active" ? "No active requests" : "No closed requests yet"}
            action={tab === "active" && user.can.submit_requests && <Link className="btn btn-secondary" to="/requests/new">New request</Link>}>
            {tab === "active" ? "When you request an item it appears here with its status." : "Fulfilled, rejected, cancelled and expired requests are kept here."}
          </Empty>
        ) : (
          <ul className="list">
            {items.map((r) => (
              <li key={r.id}>
                <Link to={`/requests/${r.id}`} className="row">
                  <div style={{ minWidth: 0 }}>
                    <div className="row-title">{r.asset?.name || r.purpose}</div>
                    <div className="row-meta">
                      <span className="num">{r.request_code}</span>, {r.quantity} needed by {fmtDate(r.required_date)}
                      {r.asset ? `, from ${r.asset.department.name}` : ", no item selected yet"}
                    </div>
                  </div>
                  <div className="row-side">
                    <span className="faint">{relative(r.updated_at)}</span>
                    {r.queued ? <span className="status amber">Waiting list</span> : <Status value={r.status} />}
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
