import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button, Confidence, ErrorState, Field, Icon, Input, LoadingRows, Notice, Select, Textarea } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { todayISO } from "../lib/format.js";
import { hasRole, useSession, useToast } from "../lib/session.jsx";

const EMPTY = {
  name: "", description: "", category: "", subcategory: "", tags: "", material: "", quantity: "1",
  condition: "", campus: "", building: "", room: "", purchase_date: "", estimated_value: "",
  department_id: "", custodian_id: "", publish_now: false, availability_note: "", available_until: "",
};

function validate(f, isEdit) {
  const e = {};
  if (f.name.trim().length < 2) e.name = "Enter a name of at least 2 characters.";
  if (!f.category) e.category = "Choose a category.";
  if (!f.condition) e.condition = "Choose the condition.";
  const q = Number(f.quantity);
  if (!Number.isInteger(q) || q < 1) e.quantity = "Enter a whole number of at least 1.";
  if (!f.campus) e.campus = "Choose a campus.";
  if (!f.building) e.building = "Choose a building.";
  if (f.estimated_value !== "" && (Number.isNaN(Number(f.estimated_value)) || Number(f.estimated_value) < 0))
    e.estimated_value = "Enter a value of 0 or more.";
  if (f.purchase_date && f.purchase_date > todayISO()) e.purchase_date = "Purchase date cannot be in the future.";
  const tags = splitTags(f.tags);
  if (tags.length > 8) e.tags = "Use at most 8 tags.";
  if (!isEdit && f.publish_now && f.available_until && f.available_until < todayISO())
    e.available_until = "Choose today or a later date.";
  return e;
}

function splitTags(s) {
  return [...new Set(s.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean))];
}

function SuggestionPanel({ s, notice, onAccept, onDismiss, applied }) {
  return (
    <section className="ai-panel" aria-label="Suggested details">
      <div className="ai-head">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="sparkle" size={16} /> Suggested details
        </h3>
        <Confidence value={s.confidence} low={s.low_confidence} />
      </div>
      <dl className="facts" style={{ gridTemplateColumns: "120px minmax(0,1fr)", fontSize: 14 }}>
        <dt>Category</dt><dd>{s.category}{s.subcategory ? `, ${s.subcategory}` : ""}</dd>
        {s.suggested_condition && (<><dt>Condition</dt><dd>{s.suggested_condition}</dd></>)}
        <dt>Material</dt><dd>{s.material}</dd>
        <dt>Tags</dt><dd>{s.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</dd>
        <dt>Description</dt><dd>{s.standard_description}</dd>
      </dl>
      <p className="muted small" style={{ marginTop: 12 }}>Why: {s.reason}</p>
      {s.missing_information.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <p className="small" style={{ fontWeight: 500 }}>Worth adding</p>
          <ul className="small muted" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {s.missing_information.map((m) => <li key={m}>{m}</li>)}
          </ul>
        </div>
      )}
      <div className="btn-row" style={{ marginTop: 16 }}>
        <Button variant="primary" size="sm" onClick={onAccept} disabled={applied}>
          {applied ? "Applied" : "Use these details"}
        </Button>
        <Button size="sm" onClick={onDismiss}>Dismiss</Button>
        <span className="ai-source">{notice || `Source: ${s.model_version}`}</span>
      </div>
      <p className="faint small" style={{ marginTop: 10 }}>
        Suggestions are advice only. Review and edit the fields before saving.
      </p>
    </section>
  );
}

export default function AssetFormPage() {
  const { id } = useParams();
  const isEdit = !!id;
  const { user, meta } = useSession();
  const navigate = useNavigate();
  const toast = useToast();
  const [f, setF] = useState({ ...EMPTY, campus: user.department.campus, building: user.department.building });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loadState, setLoadState] = useState({ loading: isEdit, error: null });
  const [ai, setAi] = useState(null);          // { suggestion, log_id, notice }
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState(null);
  const [aiDecision, setAiDecision] = useState(null); // accepted | dismissed
  const [applied, setApplied] = useState(null);       // snapshot of applied values

  const isAdmin = hasRole(user, "admin");
  const canPickCustodian = hasRole(user, "admin", "dept_rep");

  useEffect(() => {
    if (!isEdit) return;
    api.get(`/assets/${id}`).then(({ asset: a }) => {
      setF({
        ...EMPTY, name: a.name, description: a.description || "", category: a.category, subcategory: a.subcategory || "",
        tags: (a.tags || []).join(", "), material: a.material || "", quantity: String(a.quantity), condition: a.condition,
        campus: a.campus, building: a.building, room: a.room || "", purchase_date: a.purchase_date || "",
        estimated_value: a.estimated_value ?? "", custodian_id: String(a.custodian?.id || ""),
        department_id: String(a.department.id),
      });
      setLoadState({ loading: false, error: a.actions.can_edit ? null : new Error("You cannot edit this asset.") });
    }).catch((err) => setLoadState({ loading: false, error: err }));
  }, [id, isEdit]);

  const set = (k) => (e) => {
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setF((prev) => {
      const next = { ...prev, [k]: v };
      if (k === "category") next.subcategory = "";
      if (k === "campus") next.building = "";
      if (k === "department_id") next.custodian_id = "";
      return next;
    });
    if (errors[k]) setErrors((x) => ({ ...x, [k]: undefined }));
  };

  const subcats = useMemo(() => meta?.categories.find((c) => c.name === f.category)?.subcategories || [], [meta, f.category]);
  const buildings = meta?.locations[f.campus] || [];
  const deptId = Number(f.department_id || user.department.id);
  const custodians = (meta?.custodians || []).filter((c) => c.department_id === deptId);

  const suggest = async () => {
    if (f.name.trim().length < 2) {
      setErrors((x) => ({ ...x, name: "Enter a name first so details can be suggested." }));
      return;
    }
    setAiBusy(true);
    setAiError(null);
    try {
      const d = await api.post("/ai/classify", { name: f.name, description: f.description });
      setAi(d);
      setAiDecision(null);
      setApplied(null);
    } catch (ex) {
      setAiError(ex.message);
    } finally {
      setAiBusy(false);
    }
  };

  const accept = () => {
    const s = ai.suggestion;
    const vals = {
      category: s.category, subcategory: s.subcategory || "", tags: s.tags.join(", "),
      material: s.material?.replace(" (typical)", "") || "",
      description: f.description.trim() ? f.description : s.standard_description,
      ...(s.suggested_condition && !f.condition ? { condition: s.suggested_condition } : {}),
    };
    setF((prev) => ({ ...prev, ...vals }));
    setApplied(vals);
    setAiDecision("accepted");
    setErrors({});
  };

  const decisionForSave = () => {
    if (!ai) return null;
    if (aiDecision === "dismissed") return "dismissed";
    if (!applied) return "edited";
    const changed = Object.entries(applied).some(([k, v]) => (f[k] ?? "") !== v);
    return changed ? "edited" : "accepted";
  };

  const save = async (e) => {
    e.preventDefault();
    const v = validate(f, isEdit);
    setErrors(v);
    setFormError(null);
    if (Object.keys(v).length) {
      setFormError("Please correct the highlighted fields.");
      document.querySelector("[aria-invalid='true']")?.focus();
      return;
    }
    const body = {
      name: f.name, description: f.description, category: f.category, subcategory: f.subcategory || null,
      tags: splitTags(f.tags), material: f.material || null, quantity: Number(f.quantity), condition: f.condition,
      campus: f.campus, building: f.building, room: f.room || null, purchase_date: f.purchase_date || null,
      estimated_value: f.estimated_value === "" ? null : Number(f.estimated_value),
      custodian_id: f.custodian_id ? Number(f.custodian_id) : null,
    };
    if (!isEdit) {
      Object.assign(body, {
        department_id: isAdmin && f.department_id ? Number(f.department_id) : null,
        publish_now: f.publish_now, availability_note: f.availability_note || null,
        available_until: f.available_until || null, ai_log_id: ai?.log_id || null, ai_decision: decisionForSave(),
      });
    }
    setSaving(true);
    try {
      const d = isEdit ? await api.put(`/assets/${id}`, body) : await api.post("/assets", body);
      toast(isEdit ? "Changes saved" : f.publish_now ? `${d.asset.asset_code} registered and published` : `${d.asset.asset_code} registered`);
      navigate(`/assets/${d.asset.id}`);
    } catch (ex) {
      setErrors(ex.fields || {});
      setFormError(ex.message);
    } finally {
      setSaving(false);
    }
  };

  if (!user.can.register_assets) {
    return <div className="page page-narrow"><Notice tone="warn">Your role cannot register or edit assets.</Notice></div>;
  }
  if (loadState.error) return <div className="page page-narrow"><ErrorState error={loadState.error} /></div>;
  if (loadState.loading) return <div className="page page-narrow"><div className="panel"><LoadingRows /></div></div>;

  return (
    <div className="page" style={{ maxWidth: 1080 }}>
      <Link to={isEdit ? `/assets/${id}` : "/assets"} className="back">{isEdit ? "Back to asset" : "Back to marketplace"}</Link>
      <div className="page-head">
        <div>
          <h1>{isEdit ? "Edit asset" : "Register an asset"}</h1>
          <p>{isEdit ? "Previous values are kept in the asset's history." : "Describe the item, then let the system suggest a category and tags. You decide what is saved."}</p>
        </div>
      </div>

      <form onSubmit={save} noValidate>
        <div className="grid-2" style={{ gridTemplateColumns: "minmax(0,1fr) 360px" }}>
          <div className="panel panel-pad">
            {formError && <div style={{ marginBottom: 20 }}><Notice tone="error">{formError}</Notice></div>}

            <fieldset className="form-section">
              <legend>What is it?</legend>
              <div className="form-grid">
                <Field label="Name" className="span-2" error={errors.name} hint="For example: Dell 24-inch monitor">
                  {(p) => <Input {...p} value={f.name} onChange={set("name")} maxLength={160} />}
                </Field>
                <Field label="Description" className="span-2" optional error={errors.description}
                  hint="Brand, model, specifications and any wear or faults.">
                  {(p) => <Textarea {...p} rows={4} value={f.description} onChange={set("description")} maxLength={2000} />}
                </Field>
                {!isEdit && (
                  <div className="span-2 btn-row">
                    <Button type="button" onClick={suggest} loading={aiBusy}>
                      {!aiBusy && <Icon name="sparkle" size={16} />} Suggest category and tags
                    </Button>
                    {aiError && <span className="small" style={{ color: "var(--red)" }}>{aiError} You can still pick a category yourself.</span>}
                  </div>
                )}
                <Field label="Category" error={errors.category}>
                  {(p) => (
                    <Select {...p} value={f.category} onChange={set("category")}>
                      <option value="">Choose…</option>
                      {meta?.categories.map((c) => <option key={c.name}>{c.name}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Subcategory" optional error={errors.subcategory}>
                  {(p) => (
                    <Select {...p} value={f.subcategory} onChange={set("subcategory")} disabled={!subcats.length}>
                      <option value="">{f.category ? "Choose…" : "Choose a category first"}</option>
                      {subcats.map((s) => <option key={s}>{s}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Tags" optional error={errors.tags} hint="Separate with commas, up to 8.">
                  {(p) => <Input {...p} value={f.tags} onChange={set("tags")} />}
                </Field>
                <Field label="Material" optional error={errors.material}>
                  {(p) => <Input {...p} value={f.material} onChange={set("material")} maxLength={80} />}
                </Field>
              </div>
            </fieldset>

            <fieldset className="form-section">
              <legend>Quantity and condition</legend>
              <div className="form-grid">
                <Field label="Quantity" error={errors.quantity}>
                  {(p) => <Input {...p} type="number" min="1" step="1" inputMode="numeric" value={f.quantity} onChange={set("quantity")} />}
                </Field>
                <Field label="Condition" error={errors.condition}>
                  {(p) => (
                    <Select {...p} value={f.condition} onChange={set("condition")}>
                      <option value="">Choose…</option>
                      {meta?.conditions.map((c) => <option key={c}>{c}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Purchase date" optional error={errors.purchase_date}>
                  {(p) => <Input {...p} type="date" max={todayISO()} value={f.purchase_date} onChange={set("purchase_date")} />}
                </Field>
                <Field label="Estimated value (AED)" optional error={errors.estimated_value}>
                  {(p) => <Input {...p} type="number" min="0" step="1" inputMode="decimal" value={f.estimated_value} onChange={set("estimated_value")} />}
                </Field>
              </div>
            </fieldset>

            <fieldset className="form-section">
              <legend>Ownership and location</legend>
              <div className="form-grid">
                {isAdmin && !isEdit && (
                  <Field label="Owning department" error={errors.department_id}>
                    {(p) => (
                      <Select {...p} value={f.department_id} onChange={set("department_id")}>
                        <option value="">{user.department.name}</option>
                        {meta?.departments.filter((d) => d.id !== user.department.id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                      </Select>
                    )}
                  </Field>
                )}
                {canPickCustodian && (
                  <Field label="Custodian" error={errors.custodian_id} optional={!isAdmin}
                    hint={!isEdit ? "Defaults to the department's custodian." : undefined}>
                    {(p) => (
                      <Select {...p} value={f.custodian_id} onChange={set("custodian_id")}>
                        <option value="">{isEdit ? "Keep current" : "Default"}</option>
                        {custodians.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </Select>
                    )}
                  </Field>
                )}
                <Field label="Campus" error={errors.campus}>
                  {(p) => (
                    <Select {...p} value={f.campus} onChange={set("campus")}>
                      <option value="">Choose…</option>
                      {meta && Object.keys(meta.locations).map((c) => <option key={c}>{c}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Building" error={errors.building}>
                  {(p) => (
                    <Select {...p} value={f.building} onChange={set("building")} disabled={!f.campus}>
                      <option value="">Choose…</option>
                      {buildings.map((b) => <option key={b}>{b}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Room" optional error={errors.room}>
                  {(p) => <Input {...p} value={f.room} onChange={set("room")} maxLength={30} />}
                </Field>
              </div>
            </fieldset>

            {!isEdit && (
              <fieldset className="form-section">
                <legend>Marketplace</legend>
                <label className="check">
                  <input type="checkbox" checked={f.publish_now} onChange={set("publish_now")} />
                  <span>
                    Publish as surplus now
                    <span className="muted small" style={{ display: "block" }}>Other departments can find and request it straight away.</span>
                  </span>
                </label>
                {f.publish_now && (
                  <div className="form-grid" style={{ marginTop: 16 }}>
                    <Field label="Availability note" optional className="span-2">
                      {(p) => <Input {...p} value={f.availability_note} onChange={set("availability_note")} maxLength={500} />}
                    </Field>
                    <Field label="List until" optional error={errors.available_until}>
                      {(p) => <Input {...p} type="date" min={todayISO()} value={f.available_until} onChange={set("available_until")} />}
                    </Field>
                  </div>
                )}
              </fieldset>
            )}

            <div className="form-actions">
              <Link className="btn btn-secondary" to={isEdit ? `/assets/${id}` : "/assets"}>Cancel</Link>
              <Button variant="primary" type="submit" loading={saving}>{isEdit ? "Save changes" : "Register asset"}</Button>
            </div>
          </div>

          <aside className="sticky stack">
            {ai && aiDecision !== "dismissed" ? (
              <SuggestionPanel s={ai.suggestion} notice={ai.notice} applied={aiDecision === "accepted"}
                onAccept={accept} onDismiss={() => setAiDecision("dismissed")} />
            ) : (
              !isEdit && (
                <div className="panel panel-pad">
                  <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}><Icon name="sparkle" size={16} /> Suggested details</h3>
                  <p className="muted small" style={{ marginTop: 6 }}>
                    {aiDecision === "dismissed"
                      ? "Suggestion dismissed. Fill in the category yourself, or ask again after changing the description."
                      : "Enter a name and description, then choose “Suggest category and tags”. You can accept, edit or dismiss what comes back."}
                  </p>
                  {meta?.ai && <p className="faint small" style={{ marginTop: 10 }}>{meta.ai.label}</p>}
                </div>
              )
            )}
          </aside>
        </div>
      </form>
    </div>
  );
}
