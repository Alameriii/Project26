import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApproveDialog, RejectDialog } from "../components/DecisionDialogs.jsx";
import MatchList, { ExcludedSummary, MatchSource } from "../components/MatchList.jsx";
import { Button, Empty, ErrorState, LoadingRows, Modal, Notice, Status, Textarea, Field, Timeline } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDate } from "../lib/format.js";
import { useToast } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";
import { requestBody } from "./NewRequestPage.jsx";

function CancelDialog({ request, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const toast = useToast();
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/requests/${request.id}/cancel`, { reason: reason || null });
      toast(`${request.request_code} cancelled`);
      onDone();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Cancel ${request.request_code}?`} onClose={onClose}
      description="Any reservation is released and the next person in line is offered the item.">
      <form onSubmit={submit} className="stack">
        {err && <Notice tone="error">{err}</Notice>}
        <Field label="Reason" optional>
          {(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Keep request</Button>
          <Button variant="danger" type="submit" loading={busy}>Cancel request</Button>
        </div>
      </form>
    </Modal>
  );
}

function OpenRequestMatcher({ request, onDone }) {
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const toast = useToast();
  const find = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = { ...request, required_date: request.required_date < new Date().toISOString().slice(0, 10) ? new Date().toISOString().slice(0, 10) : request.required_date };
      const d = await api.post("/ai/match", requestBody({ ...r, quantity: String(r.quantity) }));
      setResult(d);
      setSelected(d.matches[0]?.asset.id ?? null);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  const choose = async () => {
    setBusy(true);
    try {
      await api.post(`/requests/${request.id}/select-asset`, { asset_id: selected, match_log_id: result.log_id });
      toast(`${request.request_code} submitted`);
      onDone();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel panel-pad">
      <div className="section-title">
        <h2>Find an item for this request</h2>
        <Button size="sm" onClick={find} loading={busy && !result}>{result ? "Search again" : "Find matches"}</Button>
      </div>
      <p className="muted small">This request is open because no item was chosen. You are notified when a strong match is published.</p>
      {err && <div style={{ marginTop: 12 }}><Notice tone="error">{err}</Notice></div>}
      {result && (
        <div style={{ marginTop: 16 }}>
          <MatchSource result={result} />
          {result.matches.length === 0 ? (
            <Empty title="Still no suitable items">Check again later; your request stays open.</Empty>
          ) : (
            <>
              <MatchList matches={result.matches} selected={selected} onSelect={setSelected} />
              <ExcludedSummary excluded={result.excluded} considered={result.considered} />
              <div className="form-actions">
                <Button variant="primary" onClick={choose} loading={busy} disabled={!selected}>Request selected item</Button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

export default function RequestDetailPage() {
  const { id } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.get(`/requests/${id}`), [id]);
  const [dialog, setDialog] = useState(null);
  const toast = useToast();

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;
  if (loading && !data) return <div className="page"><div className="panel"><LoadingRows rows={6} /></div></div>;
  const r = data.request;
  const act = r.actions;

  const startReview = async () => {
    try {
      await api.post(`/requests/${r.id}/start-review`);
      reload();
    } catch (ex) {
      toast(ex.message, "error");
    }
  };

  return (
    <div className="page">
      <Link to={act.self_request ? "/requests" : "/approvals"} className="back">
        {act.self_request ? "Back to my requests" : "Back to approvals"}
      </Link>
      <div className="page-head">
        <div>
          <h1>{r.asset?.name || r.purpose}</h1>
          <p><span className="num">{r.request_code}</span>, requested by {r.requester.name} ({r.requester_department.name})</p>
        </div>
        {r.queued ? <span className="status amber">Waiting list, position {data.request.queue_position}</span> : <Status value={r.status} />}
      </div>

      <div className="grid-2">
        <div className="stack">
          {r.status === "Open" && act.can_select_asset && <OpenRequestMatcher request={r} onDone={reload} />}
          <section className="panel panel-pad">
            <dl className="facts">
              <dt>Purpose</dt><dd>{r.purpose}</dd>
              {r.specifications && (<><dt>Specifications</dt><dd>{r.specifications}</dd></>)}
              <dt>Category</dt><dd>{r.category}</dd>
              <dt>Quantity</dt><dd className="num">{r.quantity}</dd>
              <dt>Minimum condition</dt><dd>{r.preferred_condition}</dd>
              <dt>Urgency</dt><dd>{r.urgency}</dd>
              <dt>Deliver to</dt><dd>{[r.delivery_campus, r.delivery_building, r.delivery_room].filter(Boolean).join(", ")}</dd>
              <dt>Needed by</dt><dd>{fmtDate(r.required_date)}</dd>
              {r.asset && (
                <>
                  <dt>Item</dt>
                  <dd><Link to={`/assets/${r.asset.id}`}>{r.asset.name}</Link> <span className="faint num">{r.asset.asset_code}</span>, {r.asset.department.name}</dd>
                </>
              )}
              {r.reserved_until && (<><dt>Reserved until</dt><dd>{fmtDate(r.reserved_until)}</dd></>)}
              {r.decided_by && (
                <>
                  <dt>Decision</dt>
                  <dd>{r.status === "Rejected" ? "Rejected" : "Approved"} by {r.decided_by.name} on {fmtDate(r.decided_at)}
                    {r.decision_note && <div className="muted small">{r.status === "Rejected" ? "Reason" : "Note"}: {r.decision_note}</div>}
                  </dd>
                </>
              )}
              {data.request.transfer && (
                <>
                  <dt>Transfer</dt>
                  <dd><Link to={`/transfers/${data.request.transfer.id}`}>{data.request.transfer.transfer_code}</Link>{" "}
                    <Status value={data.request.transfer.status} /></dd>
                </>
              )}
            </dl>
          </section>

          {data.request.recommendations?.length > 0 && (
            <section className="panel panel-pad">
              <div className="section-title">
                <h2>AI match results</h2>
                <span className="muted small">{data.request.recommendations[0].model_version}</span>
              </div>
              <ul className="list">
                {data.request.recommendations.map((m) => (
                  <li key={m.rank} className="row" style={{ padding: "10px 0" }}>
                    <div style={{ minWidth: 0 }}>
                      <div className="row-title">{m.rank}. {m.asset.name} {m.selected && <span className="status green" style={{ marginLeft: 6 }}>Chosen</span>}</div>
                      <div className="row-meta" style={{ whiteSpace: "normal" }}>{m.explanation}</div>
                    </div>
                    <span className="num muted">{m.score_percent}</span>
                  </li>
                ))}
              </ul>
              <p className="faint small" style={{ marginTop: 8 }}>Advice only. The decision is made by the owning department.</p>
            </section>
          )}

          <section className="panel panel-pad">
            <div className="section-title"><h2>History</h2></div>
            <Timeline items={data.request.history} />
          </section>
        </div>

        <aside className="sticky stack">
          <section className="panel panel-pad stack">
            {act.can_decide && (
              <>
                <h3>Your decision</h3>
                {r.match_score != null && (
                  <Notice tone="info">Match score {Math.round(r.match_score * 100)}: {r.match_reason}</Notice>
                )}
                {r.queued ? (
                  <p className="muted small">This request is on the waiting list. You can reject it now, or approve it once it holds the reservation.</p>
                ) : (
                  <Button variant="primary" className="btn-block" onClick={() => setDialog("approve")} disabled={!act.can_approve}>Approve</Button>
                )}
                <Button variant="danger" className="btn-block" onClick={() => setDialog("reject")}>Reject</Button>
                {act.can_start_review && (
                  <Button variant="quiet" className="btn-block" onClick={startReview}>Mark as under review</Button>
                )}
              </>
            )}
            {act.self_request && ["Submitted", "Under Review"].includes(r.status) && (
              <p className="muted small">
                {r.queued ? "You are on the waiting list for this item." : `Waiting for ${r.asset?.department.name} to decide.`}
                {" "}Requests cannot be approved by the person who made them.
              </p>
            )}
            {r.status === "Approved" && data.request.transfer && (
              <p className="muted small">Approved. Follow the handover in <Link to={`/transfers/${data.request.transfer.id}`}>{data.request.transfer.transfer_code}</Link>.</p>
            )}
            {act.can_cancel && <Button className="btn-block" onClick={() => setDialog("cancel")}>Cancel request</Button>}
            {!act.can_decide && !act.can_cancel && !act.self_request && (
              <p className="muted small">No actions are available to you for this request.</p>
            )}
            {!act.can_decide && !act.can_cancel && act.self_request && ["Fulfilled", "Rejected", "Cancelled", "Expired"].includes(r.status) && (
              <p className="muted small">This request is closed.</p>
            )}
          </section>
        </aside>
      </div>

      {dialog === "approve" && <ApproveDialog request={r} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />}
      {dialog === "reject" && <RejectDialog request={r} onClose={() => { setDialog(null); reload(); }} onDone={() => {}} />}
      {dialog === "cancel" && <CancelDialog request={r} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />}
    </div>
  );
}
