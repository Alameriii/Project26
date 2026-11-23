import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import MatchList, { ExcludedSummary, MatchSource } from "../components/MatchList.jsx";
import { Button, Empty, Field, Input, Notice, Select, Textarea } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { todayISO } from "../lib/format.js";
import { useSession, useToast } from "../lib/session.jsx";

export function requestValidate(f) {
  const e = {};
  if (!f.category) e.category = "Choose a category.";
  if (f.purpose.trim().length < 3) e.purpose = "Describe what the item is for.";
  const q = Number(f.quantity);
  if (!Number.isInteger(q) || q < 1) e.quantity = "Enter a whole number of at least 1.";
  if (!f.delivery_campus) e.delivery_campus = "Choose a campus.";
  if (!f.delivery_building) e.delivery_building = "Choose a building.";
  if (!f.required_date) e.required_date = "Choose the date you need it by.";
  else if (f.required_date < todayISO()) e.required_date = "The date cannot be in the past.";
  return e;
}

export function requestBody(f) {
  return {
    category: f.category, purpose: f.purpose, specifications: f.specifications, quantity: Number(f.quantity),
    preferred_condition: f.preferred_condition, urgency: f.urgency, delivery_campus: f.delivery_campus,
    delivery_building: f.delivery_building, delivery_room: f.delivery_room || null, required_date: f.required_date,
  };
}

export default function NewRequestPage() {
  const { user, meta } = useSession();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const presetAsset = params.get("asset");
  const [asset, setAsset] = useState(null);
  const [assetError, setAssetError] = useState(null);
  const [f, setF] = useState({
    category: params.get("category") || "", purpose: "", specifications: "", quantity: "1",
    preferred_condition: "Fair", urgency: "Medium", delivery_campus: user.department.campus,
    delivery_building: user.department.building, delivery_room: "", required_date: todayISO(7),
  });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(null);
  const [finding, setFinding] = useState(false);
  const [saving, setSaving] = useState(false);
  const resultsRef = useRef(null);

  useEffect(() => {
    if (!presetAsset) return;
    api.get(`/assets/${presetAsset}`).then(({ asset: a }) => {
      setAsset(a);
      setF((x) => ({ ...x, category: a.category, purpose: x.purpose || "" }));
    }).catch((e) => setAssetError(e.message));
  }, [presetAsset]);

  const buildings = meta?.locations[f.delivery_campus] || [];
  const set = (k) => (e) => {
    const v = e.target.value;
    setF((x) => ({ ...x, [k]: v, ...(k === "delivery_campus" ? { delivery_building: "" } : {}) }));
    if (errors[k]) setErrors((x) => ({ ...x, [k]: undefined }));
    if (!asset && result) { setResult(null); setSelected(null); }
  };

  const check = () => {
    const v = requestValidate(f);
    if (asset && Number(f.quantity) > asset.quantity) v.quantity = `Only ${asset.quantity} available.`;
    setErrors(v);
    if (Object.keys(v).length) {
      setFormError("Please correct the highlighted fields.");
      return false;
    }
    setFormError(null);
    return true;
  };

  const findMatches = async (e) => {
    e?.preventDefault();
    if (!check()) return;
    setFinding(true);
    try {
      const d = await api.post("/ai/match", requestBody(f));
      setResult(d);
      setSelected(d.matches[0]?.asset.id ?? null);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (ex) {
      setErrors(ex.fields || {});
      setFormError(ex.message);
    } finally {
      setFinding(false);
    }
  };

  const submit = async ({ open = false } = {}) => {
    if (!check()) return;
    const assetId = asset ? asset.id : open ? null : selected;
    if (!assetId && !open) { setFormError("Select one of the matches, or save the request as open."); return; }
    setSaving(true);
    try {
      const d = await api.post("/requests", {
        ...requestBody(f), asset_id: assetId, save_as_open: open, match_log_id: result?.log_id || null,
      });
      const r = d.request;
      toast(open ? `${r.request_code} saved as an open request`
        : r.queued ? `${r.request_code} submitted and added to the waiting list` : `${r.request_code} submitted`);
      navigate(`/requests/${r.id}`);
    } catch (ex) {
      setErrors(ex.fields || {});
      setFormError(ex.message);
    } finally {
      setSaving(false);
    }
  };

  const sortedCats = useMemo(() => meta?.categories || [], [meta]);

  if (!user.can.submit_requests) {
    return <div className="page page-narrow"><Notice tone="warn">Your role cannot submit resource requests.</Notice></div>;
  }

  return (
    <div className="page" style={{ maxWidth: 900 }}>
      <Link to={asset ? `/assets/${asset.id}` : "/requests"} className="back">{asset ? "Back to item" : "Back to my requests"}</Link>
      <div className="page-head">
        <div>
          <h1>{asset ? "Request this item" : "New request"}</h1>
          <p>
            {asset
              ? "Tell the owning department what you need it for. They approve or reject the request."
              : "Describe what you need. The system ranks surplus items that fit, and you choose. Nothing is reserved until you submit."}
          </p>
        </div>
      </div>

      {assetError && <Notice tone="error">{assetError}</Notice>}
      {asset && (
        <div className="panel panel-pad" style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <strong style={{ fontWeight: 600 }}>{asset.name}</strong> <span className="faint small num">{asset.asset_code}</span>
            <p className="muted small">{asset.department.name}, {asset.location}, {asset.quantity} available, {asset.condition}</p>
          </div>
          {asset.status === "Reserved" && <Notice tone="warn">Already reserved. Your request joins the waiting list.</Notice>}
        </div>
      )}

      <form className="panel panel-pad" onSubmit={asset ? (e) => { e.preventDefault(); submit(); } : findMatches} noValidate>
        {formError && <div style={{ marginBottom: 20 }}><Notice tone="error">{formError}</Notice></div>}
        <div className="form-grid">
          <Field label="Category" error={errors.category}>
            {(p) => (
              <Select {...p} value={f.category} onChange={set("category")} disabled={!!asset}>
                <option value="">Choose…</option>
                {sortedCats.map((c) => <option key={c.name}>{c.name}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Quantity" error={errors.quantity}>
            {(p) => <Input {...p} type="number" min="1" step="1" inputMode="numeric" value={f.quantity} onChange={set("quantity")} />}
          </Field>
          <Field label="Purpose" className="span-2" error={errors.purpose} hint="For example: seating for the new robotics lab">
            {(p) => <Input {...p} value={f.purpose} onChange={set("purpose")} maxLength={1000} />}
          </Field>
          <Field label="Specifications" optional className="span-2" error={errors.specifications}
            hint="Size, model, features or anything else that matters.">
            {(p) => <Textarea {...p} rows={3} value={f.specifications} onChange={set("specifications")} maxLength={1000} />}
          </Field>
          <Field label="Minimum condition" error={errors.preferred_condition}>
            {(p) => (
              <Select {...p} value={f.preferred_condition} onChange={set("preferred_condition")}>
                {meta?.conditions.map((c) => <option key={c} value={c}>{c} or better</option>)}
              </Select>
            )}
          </Field>
          <Field label="Urgency">
            {(p) => (
              <Select {...p} value={f.urgency} onChange={set("urgency")}>
                {meta?.urgencies.map((u) => <option key={u}>{u}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Deliver to campus" error={errors.delivery_campus}>
            {(p) => (
              <Select {...p} value={f.delivery_campus} onChange={set("delivery_campus")}>
                <option value="">Choose…</option>
                {meta && Object.keys(meta.locations).map((c) => <option key={c}>{c}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Building" error={errors.delivery_building}>
            {(p) => (
              <Select {...p} value={f.delivery_building} onChange={set("delivery_building")} disabled={!f.delivery_campus}>
                <option value="">Choose…</option>
                {buildings.map((b) => <option key={b}>{b}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Room" optional>
            {(p) => <Input {...p} value={f.delivery_room} onChange={set("delivery_room")} maxLength={30} />}
          </Field>
          <Field label="Needed by" error={errors.required_date}>
            {(p) => <Input {...p} type="date" min={todayISO()} value={f.required_date} onChange={set("required_date")} />}
          </Field>
        </div>
        <div className="form-actions">
          {asset ? (
            <Button variant="primary" type="submit" loading={saving}>
              {asset.status === "Reserved" ? "Join the waiting list" : "Submit request"}
            </Button>
          ) : (
            <Button variant={result ? "secondary" : "primary"} type="submit" loading={finding}>
              {result ? "Find matches again" : "Find matches"}
            </Button>
          )}
        </div>
      </form>

      {!asset && result && (
        <section ref={resultsRef} style={{ marginTop: 28, scrollMarginTop: 80 }}>
          <div className="section-title">
            <h2>Suggested matches</h2>
            <span className="muted small">Top {result.matches.length}, ranked by score out of 100</span>
          </div>
          <MatchSource result={result} />
          {result.matches.length === 0 ? (
            <div className="panel">
              <Empty title="No suitable items right now"
                action={<Button variant="primary" loading={saving} onClick={() => submit({ open: true })}>Save as open request</Button>}>
                Save the request as open and you will be notified when a matching item is published.
              </Empty>
            </div>
          ) : (
            <>
              <MatchList matches={result.matches} selected={selected} onSelect={setSelected} />
              <ExcludedSummary excluded={result.excluded} considered={result.considered} />
              <div className="form-actions" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
                <Button variant="quiet" onClick={() => submit({ open: true })} disabled={saving}>
                  None of these fit, save as open request
                </Button>
                <Button variant="primary" loading={saving} onClick={() => submit()} disabled={!selected}>
                  Request selected item
                </Button>
              </div>
              <p className="faint small" style={{ textAlign: "right", marginTop: 8 }}>
                Scores are suggestions. The owning department still approves or rejects the request.
              </p>
            </>
          )}
        </section>
      )}
    </div>
  );
}
