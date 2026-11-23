import { Link } from "react-router-dom";
import { Empty, ErrorState, LoadingRows, Status } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDate, relative } from "../lib/format.js";
import { hasRole, useSession } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  const { user } = useSession();
  const { data, error, loading, reload } = useAsync(() => api.get("/dashboard"), []);
  const approver = hasRole(user, "admin", "dept_rep");

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{greeting()}, {user.name.split(" ")[0]}</h1>
          <p>{user.role_labels.join(", ")} in {user.department.name}.</p>
        </div>
        <div className="btn-row">
          {user.can.register_assets && <Link className="btn btn-secondary" to="/assets/new">Register asset</Link>}
          {user.can.submit_requests && <Link className="btn btn-primary" to="/requests/new">New request</Link>}
        </div>
      </div>

      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <div className="panel"><LoadingRows /></div>}
      {data && (
        <>
          <div className="summary">
            <Link to="/assets">
              <strong>{data.counts.available_listings}</strong>
              <span>Items available to reuse</span>
            </Link>
            {approver ? (
              <Link to="/approvals">
                <strong>{data.counts.pending_approvals}</strong>
                <span>Requests waiting for your decision</span>
              </Link>
            ) : (
              <Link to="/requests">
                <strong>{data.counts.my_open_requests}</strong>
                <span>Your active requests</span>
              </Link>
            )}
            <Link to="/transfers">
              <strong>{data.counts.transfers_needing_action}</strong>
              <span>Transfers needing your action</span>
            </Link>
            <Link to="/assets?scope=inventory">
              <strong>{data.counts.department_assets}</strong>
              <span>Assets in {user.department.code}</span>
            </Link>
          </div>

          <div className="columns">
            {approver ? (
              <section>
                <div className="section-title">
                  <h2>Waiting for approval</h2>
                  <Link to="/approvals" className="small">View all</Link>
                </div>
                <div className="panel">
                  {data.approvals.length === 0 ? (
                    <Empty title="Nothing to review">New requests for your department's assets appear here.</Empty>
                  ) : (
                    <ul className="list">
                      {data.approvals.map((r) => (
                        <li key={r.id}>
                          <Link to={`/requests/${r.id}`} className="row">
                            <div style={{ minWidth: 0 }}>
                              <div className="row-title">{r.asset?.name}</div>
                              <div className="row-meta">
                                {r.request_code}, {r.requester.name}, {r.requester_department.name}
                              </div>
                            </div>
                            <div className="row-side">
                              {r.queued ? <span className="status">In queue</span> : <Status value={r.status} />}
                            </div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>
            ) : (
              <section>
                <div className="section-title">
                  <h2>Your recent requests</h2>
                  {user.can.submit_requests && <Link to="/requests" className="small">View all</Link>}
                </div>
                <div className="panel">
                  {data.my_requests.length === 0 ? (
                    <Empty title="No requests yet"
                      action={user.can.submit_requests && <Link className="btn btn-secondary" to="/requests/new">New request</Link>}>
                      {user.can.submit_requests
                        ? "Describe what you need and the system will suggest matching surplus items."
                        : "Your role can browse the marketplace but does not submit requests."}
                    </Empty>
                  ) : (
                    <ul className="list">
                      {data.my_requests.map((r) => (
                        <li key={r.id}>
                          <Link to={`/requests/${r.id}`} className="row">
                            <div style={{ minWidth: 0 }}>
                              <div className="row-title">{r.asset?.name || r.purpose}</div>
                              <div className="row-meta">{r.request_code}, updated {relative(r.updated_at)}</div>
                            </div>
                            <Status value={r.status} />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>
            )}

            <section>
              <div className="section-title">
                <h2>Transfers needing action</h2>
                <Link to="/transfers" className="small">View all</Link>
              </div>
              <div className="panel">
                {data.transfers.length === 0 ? (
                  <Empty title="No transfers to handle">
                    Approved transfers you need to dispatch or receive will appear here.
                  </Empty>
                ) : (
                  <ul className="list">
                    {data.transfers.map((t) => (
                      <li key={t.id}>
                        <Link to={`/transfers/${t.id}`} className="row">
                          <div style={{ minWidth: 0 }}>
                            <div className="row-title">{t.asset.name}</div>
                            <div className="row-meta">
                              {t.transfer_code}, {t.from_department.name} to {t.to_department.name},
                              {" "}{fmtDate(t.scheduled_date)}
                            </div>
                          </div>
                          <Status value={t.status} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
