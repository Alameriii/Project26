import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button, ErrorState, Field, Input, LoadingRows, Modal, Notice, Status, Textarea, Timeline } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { aed, fmtDate, todayISO } from "../lib/format.js";
import { useSession, useToast } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

function PublishDialog({ asset, onClose, onDone }) {
  const [note, setNote] = useState(asset.availability_note || "");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const toast = useToast();
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const d = await api.post(`/assets/${asset.id}/publish`, { availability_note: note || null, available_until: until || null });
      toast("Published to the marketplace");
      onDone(d.asset);
    } catch (ex) {
      setErr(ex);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Publish as surplus" onClose={onClose}
      description="The item becomes visible to every signed-in user and can be requested by other departments.">
      <form onSubmit={submit} className="stack">
        {err && <Notice tone="error">{err.message}</Notice>}
        <Field label="Availability note" optional hint="For example where to collect it, or why it is surplus.">
          {(p) => <Textarea {...p} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <Field label="List until" optional error={err?.fields?.available_until}>
          {(p) => <Input {...p} type="date" min={todayISO()} value={until} onChange={(e) => setUntil(e.target.value)} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" loading={busy}>Publish</Button>
        </div>
      </form>
    </Modal>
  );
}

function StatusDialog({ asset, onClose, onDone }) {
  const [target, setTarget] = useState(asset.actions.status_options[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const toast = useToast();
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const d = await api.post(`/assets/${asset.id}/status`, { to_status: target, note: note || null });
      toast(`Status changed to ${target}`);
      onDone(d.asset);
    } catch (ex) {
      setErr(ex);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Change status" onClose={onClose}
      description={`Currently ${asset.status}. Only moves allowed by the asset life cycle are offered.`}>
      <form onSubmit={submit} className="stack">
        {err && <Notice tone="error">{err.message}</Notice>}
        <fieldset>
          <legend className="sr-only">New status</legend>
          {asset.actions.status_options.map((s) => (
            <label key={s} className="check" style={{ marginBottom: 10 }}>
              <input type="radio" name="status" value={s} checked={target === s} onChange={() => setTarget(s)} />
              <span>{s}</span>
            </label>
          ))}
        </fieldset>
        <Field label="Note" optional>
          {(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" loading={busy}>Change status</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function AssetDetailPage() {
  const { id } = useParams();
  const { user } = useSession();
  const toast = useToast();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api.get(`/assets/${id}`), [id]);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;
  if (loading && !data) return <div className="page"><div className="panel"><LoadingRows rows={6} /></div></div>;
  const a = data.asset;
  const act = a.actions;

  const withdraw = async () => {
    setBusy(true);
    try {
      await api.post(`/assets/${a.id}/withdraw`);
      toast("Listing withdrawn");
      reload();
    } catch (ex) {
      toast(ex.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const done = () => { setDialog(null); reload(); };

  return (
    <div className="page">
      <Link to="/assets" className="back">Back to marketplace</Link>
      <div className="page-head">
        <div>
          <h1>{a.name}</h1>
          <p><span className="num">{a.asset_code}</span>, {a.category}{a.subcategory ? `, ${a.subcategory}` : ""}</p>
        </div>
        <Status value={a.status} />
      </div>

      <div className="grid-2">
        <div className="stack">
          <section className="panel panel-pad">
            {a.description && <p style={{ marginBottom: 20, maxWidth: "68ch" }}>{a.description}</p>}
            <dl className="facts">
              <dt>Quantity</dt><dd className="num">{a.quantity}</dd>
              <dt>Condition</dt><dd>{a.condition}</dd>
              <dt>Owning department</dt><dd>{a.department.name}</dd>
              <dt>Custodian</dt><dd>{a.custodian?.name}</dd>
              <dt>Location</dt><dd>{a.location}</dd>
              {a.material && (<><dt>Material</dt><dd>{a.material}</dd></>)}
              <dt>Purchased</dt><dd>{fmtDate(a.purchase_date)}</dd>
              {"estimated_value" in a && (<><dt>Estimated value</dt><dd className="num">{aed(a.estimated_value)}</dd></>)}
              {a.status === "Available" && (
                <>
                  <dt>Listed</dt><dd>{fmtDate(a.published_at)}{a.available_until ? `, until ${fmtDate(a.available_until)}` : ""}</dd>
                  {a.availability_note && (<><dt>Availability note</dt><dd>{a.availability_note}</dd></>)}
                </>
              )}
              {a.tags.length > 0 && (
                <>
                  <dt>Tags</dt>
                  <dd>{a.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</dd>
                </>
              )}
            </dl>
          </section>

          <section className="panel panel-pad">
            <div className="section-title">
              <h2>History</h2>
              <span className="muted small">Newest first. Entries cannot be edited.</span>
            </div>
            <Timeline items={data.history} />
          </section>
        </div>

        <aside className="sticky stack">
          <section className="panel panel-pad stack">
            {a.status === "Reserved" && a.reserved_for && (
              <Notice tone="warn">
                Reserved for {a.reserved_for.request_code} until {fmtDate(a.reserved_for.reserved_until)}.
              </Notice>
            )}
            {a.status === "Reserved" && !a.reserved_for && (
              <Notice tone="warn">Another department has reserved this item pending approval.</Notice>
            )}
            {act.can_request && (
              <>
                <Button variant="primary" className="btn-block" onClick={() => navigate(`/requests/new?asset=${a.id}`)}>
                  {act.request_will_queue ? "Join the waiting list" : "Request this item"}
                </Button>
                <p className="muted small">
                  {act.request_will_queue
                    ? "You will be next in line if the current request is rejected, cancelled or expires."
                    : "The item is held for you for 3 working days while the owning department decides."}
                </p>
              </>
            )}
            {!act.can_request && a.department.id === user.department.id && a.status === "Available" && (
              <p className="muted small">This item belongs to your department, so it cannot be requested by you.</p>
            )}
            {!act.can_request && !user.can.submit_requests && (
              <p className="muted small">Your role can view listings but does not submit requests.</p>
            )}
            {(act.can_publish || act.can_withdraw || act.can_edit || act.status_options.length > 0) && (
              <div className="stack" style={{ borderTop: act.can_request ? "1px solid var(--hairline)" : 0, paddingTop: act.can_request ? 16 : 0 }}>
                <h3>Manage</h3>
                {act.can_publish && <Button variant="primary" className="btn-block" onClick={() => setDialog("publish")}>Publish as surplus</Button>}
                {act.can_withdraw && <Button className="btn-block" loading={busy} onClick={withdraw}>Withdraw listing</Button>}
                {act.can_edit && <Link className="btn btn-secondary btn-block" to={`/assets/${a.id}/edit`}>Edit details</Link>}
                {act.status_options.length > 0 && (
                  <Button className="btn-block" onClick={() => setDialog("status")}>Change status</Button>
                )}
                {a.status === "Reserved" && <p className="muted small">Decide on the request in Approvals before changing this item.</p>}
              </div>
            )}
          </section>
          <p className="faint small" style={{ padding: "0 6px" }}>
            Allowed next states: {act.allowed_next_states.join(", ") || "none (final state)"}
          </p>
        </aside>
      </div>

      {dialog === "publish" && <PublishDialog asset={a} onClose={() => setDialog(null)} onDone={done} />}
      {dialog === "status" && <StatusDialog asset={a} onClose={() => setDialog(null)} onDone={done} />}
    </div>
  );
}
