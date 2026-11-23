import { useState } from "react";
import { Link } from "react-router-dom";
import { ApproveDialog, RejectDialog } from "../components/DecisionDialogs.jsx";
import { Button, Empty, ErrorState, LoadingRows, Notice, Status } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDate } from "../lib/format.js";
import { hasRole, useSession } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

export default function ApprovalsPage() {
  const { user } = useSession();
  const { data, error, loading, reload } = useAsync(() => api.get("/requests", { scope: "approvals" }), []);
  const [dialog, setDialog] = useState(null);

  if (!hasRole(user, "admin", "dept_rep")) {
    return <div className="page page-narrow"><Notice tone="warn">Only department representatives and administrators review requests.</Notice></div>;
  }
  const items = data?.items || [];
  const ready = items.filter((r) => !r.queued);
  const waiting = items.filter((r) => r.queued);

  const row = (r) => (
    <li key={r.id}>
      <div className="row" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
        <Link to={`/requests/${r.id}`} style={{ minWidth: 0, color: "inherit" }}>
          <div className="row-title">{r.quantity} × {r.asset?.name}</div>
          <div className="row-meta">
            <span className="num">{r.request_code}</span>, {r.requester.name} ({r.requester_department.name}),
            needed by {fmtDate(r.required_date)}, {r.urgency.toLowerCase()} urgency
          </div>
          <div className="row-meta">
            {r.match_score != null ? `Match ${Math.round(r.match_score * 100)}: ${r.match_reason}` : "Requested directly from the listing"}
          </div>
        </Link>
        <div className="row-side" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
          {r.queued ? <span className="status amber">Waiting list</span> : <Status value={r.status} />}
          {r.actions.self_request ? (
            <span className="faint small">Your own request</span>
          ) : (
            <>
              {!r.queued && r.actions.can_approve && <Button size="sm" variant="primary" onClick={() => setDialog({ type: "approve", r })}>Approve</Button>}
              {r.actions.can_decide && <Button size="sm" variant="danger" onClick={() => setDialog({ type: "reject", r })}>Reject</Button>}
            </>
          )}
        </div>
      </div>
    </li>
  );

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Approvals</h1>
          <p>
            {hasRole(user, "admin") ? "Requests for assets in every department." : `Requests for ${user.department.name} assets.`}
            {" "}Match scores are advice only; the decision is yours.
          </p>
        </div>
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      <section>
        <div className="section-title"><h2>Ready for a decision</h2><span className="muted small">{ready.length}</span></div>
        <div className="panel">
          {loading && !data ? <LoadingRows /> : ready.length === 0 ? (
            <Empty title="You're up to date">New requests for your department's items appear here.</Empty>
          ) : <ul className="list">{ready.map(row)}</ul>}
        </div>
      </section>
      {waiting.length > 0 && (
        <section style={{ marginTop: 28 }}>
          <div className="section-title">
            <h2>Waiting list</h2>
            <span className="muted small">Offered the item in order if the request ahead is not approved</span>
          </div>
          <div className="panel"><ul className="list">{waiting.map(row)}</ul></div>
        </section>
      )}

      {dialog?.type === "approve" && (
        <ApproveDialog request={dialog.r} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />
      )}
      {dialog?.type === "reject" && (
        <RejectDialog request={dialog.r} onClose={() => { setDialog(null); reload(); }} onDone={() => {}} />
      )}
    </div>
  );
}
