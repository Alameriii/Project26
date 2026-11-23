import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { todayISO } from "../lib/format.js";
import { useSession, useToast } from "../lib/session.jsx";
import { Button, Field, Input, Modal, Notice, Select, Textarea } from "./ui.jsx";

export function ApproveDialog({ request, onClose, onDone }) {
  const { meta } = useSession();
  const toast = useToast();
  const [method, setMethod] = useState("Delivery");
  const [date, setDate] = useState(todayISO(1));
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const partial = request.asset && request.quantity < request.asset.quantity;

  const submit = async (e) => {
    e.preventDefault();
    if (!date || date < todayISO()) { setErr({ message: "Choose today or a later date.", fields: { scheduled_date: "Choose today or a later date." } }); return; }
    setBusy(true);
    setErr(null);
    try {
      const d = await api.post(`/requests/${request.id}/approve`, { method, scheduled_date: date, note: note || null });
      toast(`${request.request_code} approved. Transfer ${d.transfer.transfer_code} scheduled`);
      onDone(d);
    } catch (ex) {
      setErr(ex);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Approve ${request.request_code}`} onClose={onClose}
      description={`${request.quantity} × ${request.asset?.name} goes to ${request.requester_department.name}. Ownership changes only when they confirm receipt.`}>
      <form onSubmit={submit} className="stack">
        {err && <Notice tone="error">{err.message}</Notice>}
        {partial && (
          <Notice tone="info">
            {request.quantity} of {request.asset.quantity} units are requested. The approved units become their own
            asset record and the rest stay listed.
          </Notice>
        )}
        <div className="form-grid">
          <Field label="Handover method">
            {(p) => (
              <Select {...p} value={method} onChange={(e) => setMethod(e.target.value)}>
                {meta?.transfer_methods.map((m) => <option key={m}>{m}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Transfer date" error={err?.fields?.scheduled_date}>
            {(p) => <Input {...p} type="date" min={todayISO()} value={date} onChange={(e) => setDate(e.target.value)} />}
          </Field>
        </div>
        <Field label="Note to the requester" optional>
          {(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" loading={busy}>Approve and schedule transfer</Button>
        </div>
      </form>
    </Modal>
  );
}

export function RejectDialog({ request, onClose, onDone }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [alternatives, setAlternatives] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (reason.trim().length < 5) { setErr({ message: "Give a reason of at least 5 characters.", field: true }); return; }
    setBusy(true);
    setErr(null);
    try {
      const d = await api.post(`/requests/${request.id}/reject`, { reason });
      toast(`${request.request_code} rejected`);
      setAlternatives(d.alternatives);
      onDone(d, { keepOpen: true });
    } catch (ex) {
      setErr(ex);
    } finally {
      setBusy(false);
    }
  };

  if (alternatives) {
    return (
      <Modal title="Request rejected" onClose={onClose}
        description="The requester has been told the reason. These alternatives were suggested to them:">
        {alternatives.length === 0 ? (
          <p className="muted">No other suitable items are available right now.</p>
        ) : (
          <ul className="list panel" style={{ marginBottom: 8 }}>
            {alternatives.map((a) => (
              <li key={a.asset_id}>
                <Link className="row" to={`/assets/${a.asset_id}`} onClick={onClose}>
                  <div style={{ minWidth: 0 }}>
                    <div className="row-title">{a.name}</div>
                    <div className="row-meta">{a.reason}</div>
                  </div>
                  <span className="num muted">{a.score_percent}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="form-actions"><Button variant="primary" onClick={onClose}>Done</Button></div>
      </Modal>
    );
  }

  return (
    <Modal title={`Reject ${request.request_code}`} onClose={onClose}
      description="The reservation is released and the requester sees your reason together with other available items.">
      <form onSubmit={submit} className="stack">
        {err && !err.field && <Notice tone="error">{err.message}</Notice>}
        <Field label="Reason" error={err?.field ? err.message : err?.fields?.reason}>
          {(p) => <Textarea {...p} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />}
        </Field>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Cancel</Button>
          <Button variant="danger" type="submit" loading={busy}>Reject request</Button>
        </div>
      </form>
    </Modal>
  );
}
