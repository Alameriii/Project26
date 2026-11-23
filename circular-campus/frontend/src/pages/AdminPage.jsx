import { useState } from "react";
import { Button, Empty, ErrorState, Field, Input, LoadingRows, Modal, Notice, Select } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { useSession, useToast } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

function UserDialog({ onClose, onDone }) {
  const { meta } = useSession();
  const toast = useToast();
  const [f, setF] = useState({ name: "", email: "", password: "", department_id: "", roles: [] });
  const [errors, setErrors] = useState({});
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const toggle = (r) => setF((x) => ({ ...x, roles: x.roles.includes(r) ? x.roles.filter((y) => y !== r) : [...x.roles, r] }));
  const submit = async (e) => {
    e.preventDefault();
    const v = {};
    if (f.name.trim().length < 2) v.name = "Enter the person's name.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) v.email = "Enter a valid email address.";
    if (f.password.length < 8) v.password = "Use at least 8 characters.";
    if (!f.department_id) v.department_id = "Choose a department.";
    if (!f.roles.length) v.roles = "Choose at least one role.";
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      await api.post("/admin/users", { ...f, department_id: Number(f.department_id) });
      toast(`Account created for ${f.name}`);
      onDone();
    } catch (ex) {
      setErrors(ex.fields || {});
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Add a user" onClose={onClose} description="The person signs in with this email and password.">
      <form onSubmit={submit} className="stack" noValidate>
        {err && <Notice tone="error">{err}</Notice>}
        <Field label="Name" error={errors.name}>{(p) => <Input {...p} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
        <Field label="University email" error={errors.email}>{(p) => <Input {...p} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
        <Field label="Temporary password" error={errors.password} hint="At least 8 characters.">{(p) => <Input {...p} type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />}</Field>
        <Field label="Department" error={errors.department_id}>
          {(p) => (
            <Select {...p} value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })}>
              <option value="">Choose…</option>
              {meta?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          )}
        </Field>
        <fieldset>
          <legend className="field" style={{ fontSize: 13.5, fontWeight: 500, marginBottom: 8 }}>Roles</legend>
          {meta?.roles.map((r) => (
            <label key={r.value} className="check" style={{ marginBottom: 8 }}>
              <input type="checkbox" checked={f.roles.includes(r.value)} onChange={() => toggle(r.value)} />
              <span>{r.label}</span>
            </label>
          ))}
          {errors.roles && <div className="field"><div className="error">{errors.roles}</div></div>}
        </fieldset>
        <div className="form-actions">
          <Button type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" loading={busy}>Add user</Button>
        </div>
      </form>
    </Modal>
  );
}

function Users() {
  const { user: me } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(() => api.get("/admin/users"), []);
  const [adding, setAdding] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const setActive = async (u, active) => {
    try {
      await api.patch(`/admin/users/${u.id}`, { active });
      toast(active ? `${u.name} reactivated` : `${u.name} deactivated`);
      setConfirm(null);
      reload();
    } catch (ex) {
      toast(ex.message, "error");
    }
  };
  return (
    <>
      <div className="section-title">
        <h2>Users</h2>
        <Button variant="primary" size="sm" onClick={() => setAdding(true)}>Add user</Button>
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      <div className="panel table-wrap">
        {loading && !data ? <LoadingRows /> : (
          <table className="table">
            <thead><tr><th>Name</th><th>Department</th><th>Roles</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id}>
                  <td><div>{u.name}</div><div className="muted small">{u.email}</div></td>
                  <td>{u.department.name}</td>
                  <td>{u.role_labels.join(", ")}</td>
                  <td>{u.active ? <span className="status green">Active</span> : <span className="status">Deactivated</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    {u.id !== me.id && (u.active
                      ? <Button size="sm" variant="danger" onClick={() => setConfirm(u)}>Deactivate</Button>
                      : <Button size="sm" onClick={() => setActive(u, true)}>Reactivate</Button>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {adding && <UserDialog onClose={() => setAdding(false)} onDone={() => { setAdding(false); reload(); }} />}
      {confirm && (
        <Modal title={`Deactivate ${confirm.name}?`} onClose={() => setConfirm(null)}
          description="They will be signed out and unable to sign in. Their history is kept. You can reactivate the account later.">
          <div className="form-actions">
            <Button onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant="danger" onClick={() => setActive(confirm, false)}>Deactivate</Button>
          </div>
        </Modal>
      )}
    </>
  );
}

function Departments() {
  const { meta, reloadMeta } = useSession();
  const toast = useToast();
  const [f, setF] = useState({ code: "", name: "", campus: "", building: "" });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    const v = {};
    if (!/^[A-Za-z0-9-]{2,12}$/.test(f.code)) v.code = "2–12 letters or digits.";
    if (f.name.trim().length < 2) v.name = "Enter the department name.";
    if (!f.campus) v.campus = "Choose a campus.";
    if (!f.building) v.building = "Choose a building.";
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      await api.post("/admin/departments", f);
      toast(`${f.name} added`);
      setF({ code: "", name: "", campus: "", building: "" });
      reloadMeta();
    } catch (ex) {
      setErrors(ex.fields || { name: ex.message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid-2">
      <div className="panel">
        <ul className="list">
          {meta?.departments.map((d) => (
            <li key={d.id} className="row">
              <div><div className="row-title">{d.name}</div><div className="row-meta">{d.campus}, {d.building}</div></div>
              <span className="faint num">{d.code}</span>
            </li>
          ))}
        </ul>
      </div>
      <form className="panel panel-pad stack" onSubmit={submit} noValidate>
        <h3>Add a department</h3>
        <Field label="Code" error={errors.code}>{(p) => <Input {...p} value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} />}</Field>
        <Field label="Name" error={errors.name}>{(p) => <Input {...p} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
        <Field label="Campus" error={errors.campus}>
          {(p) => (
            <Select {...p} value={f.campus} onChange={(e) => setF({ ...f, campus: e.target.value, building: "" })}>
              <option value="">Choose…</option>
              {meta && Object.keys(meta.locations).map((c) => <option key={c}>{c}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Building" error={errors.building}>
          {(p) => (
            <Select {...p} value={f.building} onChange={(e) => setF({ ...f, building: e.target.value })} disabled={!f.campus}>
              <option value="">Choose…</option>
              {(meta?.locations[f.campus] || []).map((b) => <option key={b}>{b}</option>)}
            </Select>
          )}
        </Field>
        <Button variant="primary" type="submit" loading={busy}>Add department</Button>
      </form>
    </div>
  );
}

function Audit() {
  const [filters, setFilters] = useState({ action: "", entity: "", date_from: "", date_to: "" });
  const [applied, setApplied] = useState(filters);
  const { data, error, loading, reload } = useAsync(() => api.get("/admin/audit", applied), [JSON.stringify(applied)]);
  return (
    <>
      <form className="btn-row" style={{ marginBottom: 16, alignItems: "flex-end" }}
        onSubmit={(e) => { e.preventDefault(); setApplied(filters); }}>
        <Field label="Action">
          {(p) => (
            <Select {...p} value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} style={{ minWidth: 200 }}>
              <option value="">Any action</option>
              {data?.actions.map((a) => <option key={a}>{a}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Record">{(p) => <Input {...p} placeholder="e.g. AST-0001" value={filters.entity} onChange={(e) => setFilters({ ...filters, entity: e.target.value })} />}</Field>
        <Field label="From">{(p) => <Input {...p} type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} />}</Field>
        <Field label="To">{(p) => <Input {...p} type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} />}</Field>
        <Button type="submit">Apply</Button>
      </form>
      {error && <ErrorState error={error} onRetry={reload} />}
      <div className="panel table-wrap">
        {loading && !data ? <LoadingRows /> : data?.items.length === 0 ? <Empty title="No entries match these filters" /> : (
          <table className="table">
            <thead><tr><th>When</th><th>User</th><th>Action</th><th>Record</th><th>Details</th></tr></thead>
            <tbody>
              {data?.items.map((r) => (
                <tr key={r.id}>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>{fmtDateTime(r.at)}</td>
                  <td>{r.user?.name || "System"}</td>
                  <td>{r.action.replace(/_/g, " ")}</td>
                  <td className="num">{r.entity_ref || "—"}</td>
                  <td className="muted small" style={{ maxWidth: 360 }}>
                    {Object.entries(r.details || {}).filter(([, v]) => v !== null && v !== "").map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("; ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="faint small" style={{ marginTop: 10 }}>The audit log is append-only. Opening it is itself recorded.</p>
    </>
  );
}

export default function AdminPage() {
  const { user } = useSession();
  const [tab, setTab] = useState("users");
  if (!user.can.manage_users) {
    return <div className="page page-narrow"><Notice tone="warn">Only system administrators can open this page.</Notice></div>;
  }
  return (
    <div className="page">
      <div className="page-head"><div><h1>Administration</h1><p>Accounts, departments and the audit trail.</p></div></div>
      <div className="tabs" role="tablist">
        {[["users", "Users"], ["departments", "Departments"], ["audit", "Audit log"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {tab === "users" && <Users />}
      {tab === "departments" && <Departments />}
      {tab === "audit" && <Audit />}
    </div>
  );
}
