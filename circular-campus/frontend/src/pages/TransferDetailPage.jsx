import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button, ErrorState, Field, Icon, LoadingRows, Modal, Notice, Select, Status, Textarea, Timeline } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDate, fmtDateTime } from "../lib/format.js";
import { useSession, useToast } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

const STEPS = ["Scheduled", "Dispatched", "Completed"];

function Progress({ status }) {
  const idx = status === "Completed" || status === "Received" ? 2 : status === "Dispatched" || status === "Disputed" ? 1 : 0;
  return (
    <ol style={{ display: "flex", gap: 8, listStyle: "none", padding: 0, margin: "0 0 4px" }} aria-label="Transfer progress">
      {STEPS.map((s, i) => (
        <li key={s} style={{ flex: 1 }}>
          <div style={{ height: 4, borderRadius: 2, background: i <= idx && status !== "Cancelled" ? (status === "Disputed" && i === 1 ? "var(--red)" : "var(--accent)") : "var(--grey-tint)" }} />
          <div className="small" style={{ marginTop: 6, color: i <= idx ? "var(--ink)" : "var(--ink-3)" }}>
            {s === "Completed" ? "Received" : s}
          </div>
        </li>
      ))}
    </ol>
  );
}

function ConfirmDialog({ t, onClose, onDone }) {
  const { meta } = useSession();
  const toast = useToast();
  const [condition, setCondition] = useState("");
  const [avoided, setAvoided] = useState("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState({});
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    const v = {};
    if (!condition) v.condition = "Choose the condition on arrival.";
    if (!avoided) v.avoided = "Choose yes or no.";
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      await api.post(`/transfers/${t.id}/confirm`, { condition_on_arrival: condition, avoided_purchase: avoided === "yes", note: note || null });
      toast(`Receipt confirmed. ${t.asset.asset_code} now belongs to ${t.to_department.name}`);
      onDone();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Confirm receipt" onClose={onClose}
      description={`Ownership, custodian and location of ${t.asset.name} change to ${t.to_department.name} when you confirm.`}>
      <form onSubmit={submit} className="stack" noValidate>
        {err && <Notice tone="error">{err}</Notice>}
        <Field label="Condition on arrival" error={errors.condition}>
          {(p) => (
            <Select {...p} value={condition} onChange={(e) => setCondition(e.target.value)}>
              <option value="">Choose…</option>
              {meta?.conditions.map((c) => <option key={c}>{c}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Did this replace a planned purchase?" error={errors.avoided}
          hint="Used for the avoided-purchase and savings figures.">
          {(p) => (
            <Select {...p} value={avoided} onChange={(e) => setAvoided(e.target.value)}>
              <option value="">Choose…</option>
              <option value="yes">Yes, we would otherwise have bought one</option>
              <option value="no">No</option>
            </Select>
          )}
        </Field>
        <Field label="Note" optional>
          {(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" loading={busy}>Confirm receipt</Button>
        </div>
      </form>
    </Modal>
  );
}

function NoteDialog({ title, description, label, action, variant, required, endpoint, field, onClose, onDone, success }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const submit = async (e) => {
    e.preventDefault();
    if (required && text.trim().length < 5) { setErr("Write at least 5 characters."); return; }
    setBusy(true);
    try {
      await api.post(endpoint, { [field]: text || null });
      toast(success);
      onDone();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} description={description} onClose={onClose}>
      <form onSubmit={submit} className="stack" noValidate>
        <Field label={label} optional={!required} error={err}>
          {(p) => <Textarea {...p} rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={500} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Back</Button>
          <Button variant={variant} type="submit" loading={busy}>{action}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function TransferDetailPage() {
  const { id } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.get(`/transfers/${id}`), [id]);
  const [dialog, setDialog] = useState(null);
  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;
  if (loading && !data) return <div className="page"><div className="panel"><LoadingRows rows={6} /></div></div>;
  const t = data.transfer;
  const act = t.actions;
  const close = () => setDialog(null);
  const done = () => { setDialog(null); reload(); };

  return (
    <div className="page">
      <Link to="/transfers" className="back">Back to transfers</Link>
      <div className="page-head">
        <div>
          <h1>{t.quantity} × {t.asset.name}</h1>
          <p><span className="num">{t.transfer_code}</span> for <Link to={`/requests/${t.request.id}`}>{t.request.request_code}</Link></p>
        </div>
        <Status value={t.status} />
      </div>

      <div className="grid-2">
        <div className="stack">
          <section className="panel panel-pad stack">
            <Progress status={t.status} />
            {t.status === "Disputed" && <Notice tone="error">Damage or loss was reported on arrival: {t.closing_note}</Notice>}
            {t.status === "Cancelled" && <Notice tone="warn">Cancelled{t.closing_note ? `: ${t.closing_note}` : "."}</Notice>}
            {t.status === "Completed" && (
              <Notice tone="success">
                Received by {t.received_by?.name} on {fmtDateTime(t.received_at)}. The asset now belongs to {t.to_department.name}.
              </Notice>
            )}
            <dl className="facts">
              <dt>From</dt><dd>{t.from_department.name}, custodian {t.from_custodian.name}</dd>
              <dt>To</dt><dd>{t.to_department.name}, received by {t.receiving_custodian.name}</dd>
              <dt>Destination</dt><dd>{t.destination}</dd>
              <dt>Method and date</dt><dd>{t.method}, {fmtDate(t.scheduled_date)}</dd>
              <dt>Approved by</dt><dd>{t.approved_by.name}, {fmtDateTime(t.approved_at)}</dd>
              {t.dispatched_by && (<><dt>Dispatched by</dt><dd>{t.dispatched_by.name}, {fmtDateTime(t.dispatched_at)}{t.handover_note && <div className="muted small">{t.handover_note}</div>}</dd></>)}
              {t.condition_on_arrival && (<><dt>Condition on arrival</dt><dd>{t.condition_on_arrival}</dd></>)}
              {t.avoided_purchase !== null && (<><dt>Avoided a purchase</dt><dd>{t.avoided_purchase ? "Yes" : "No"}</dd></>)}
              <dt>Asset</dt><dd><Link to={`/assets/${t.asset.id}`}>{t.asset.name}</Link> <span className="faint num">{t.asset.asset_code}</span>, now {t.asset.status}</dd>
            </dl>
          </section>
          <section className="panel panel-pad">
            <div className="section-title"><h2>Transfer history</h2></div>
            <Timeline items={t.history} />
          </section>
        </div>

        <aside className="sticky">
          <section className="panel panel-pad stack">
            {act.can_dispatch && (
              <>
                <h3 style={{ display: "flex", gap: 8, alignItems: "center" }}><Icon name="truck" size={16} /> Sending side</h3>
                <p className="muted small">Mark it dispatched when the item leaves. The receiver is notified.</p>
                <Button variant="primary" className="btn-block" onClick={() => setDialog("dispatch")}>Mark dispatched</Button>
                <Button className="btn-block" onClick={() => setDialog("cancel")}>Cancel transfer</Button>
              </>
            )}
            {act.can_confirm && (
              <>
                <h3>Receiving side</h3>
                <p className="muted small">Check the item, then confirm. If it arrived damaged or is missing, report it instead.</p>
                <Button variant="primary" className="btn-block" onClick={() => setDialog("confirm")}>Confirm receipt</Button>
                <Button variant="danger" className="btn-block" onClick={() => setDialog("dispute")}>Report a problem</Button>
              </>
            )}
            {!act.can_dispatch && !act.can_confirm && (
              <p className="muted small">
                {t.status === "Scheduled" ? `Waiting for ${t.from_department.name} to dispatch the item.`
                  : t.status === "Dispatched" ? `Waiting for ${t.receiving_custodian.name} to confirm receipt.`
                  : "No further actions."}
              </p>
            )}
          </section>
        </aside>
      </div>

      {dialog === "dispatch" && (
        <NoteDialog title="Mark dispatched" description="The asset moves to In Transfer and the receiver is notified."
          label="Handover note" action="Mark dispatched" variant="primary" endpoint={`/transfers/${t.id}/dispatch`}
          field="handover_note" onClose={close} onDone={done} success={`${t.transfer_code} marked dispatched`} />
      )}
      {dialog === "cancel" && (
        <NoteDialog title="Cancel transfer" description="The request is cancelled and the item returns to the marketplace."
          label="Reason" action="Cancel transfer" variant="danger" endpoint={`/transfers/${t.id}/cancel`}
          field="reason" onClose={close} onDone={done} success={`${t.transfer_code} cancelled`} />
      )}
      {dialog === "dispute" && (
        <NoteDialog title="Report a problem" description="The transfer is marked Disputed and both departments and the administrator are notified. Ownership does not change."
          label="What is wrong?" action="Report problem" variant="danger" required endpoint={`/transfers/${t.id}/dispute`}
          field="note" onClose={close} onDone={done} success="Problem reported" />
      )}
      {dialog === "confirm" && <ConfirmDialog t={t} onClose={close} onDone={done} />}
    </div>
  );
}
