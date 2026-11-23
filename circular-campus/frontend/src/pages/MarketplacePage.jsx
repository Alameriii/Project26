import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CategoryGlyph, Empty, ErrorState, Field, Icon, Input, LoadingRows, Select, Status } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { aed } from "../lib/format.js";
import { useSession } from "../lib/session.jsx";
import { useAsync } from "../lib/useAsync.js";

const FILTER_KEYS = ["q", "scope", "category", "condition", "department_id", "campus", "status", "min_quantity",
  "max_age_years", "min_value", "max_value", "sort"];

export default function MarketplacePage() {
  const { user, meta } = useSession();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) || ""])), [params]);
  const scope = filters.scope || "marketplace";
  const [q, setQ] = useState(filters.q);

  useEffect(() => setQ(filters.q), [filters.q]);
  useEffect(() => {
    const t = setTimeout(() => { if (q !== filters.q) update("q", q); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const key = params.toString();
  const { data, error, loading, reload } = useAsync(() => api.get("/assets", { ...filters, scope }), [key]);

  function update(name, value) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name === "scope") next.delete("status");
    setParams(next, { replace: true });
  }
  const clear = () => setParams(scope === "marketplace" ? {} : { scope }, { replace: true });
  const activeFilters = FILTER_KEYS.filter((k) => !["q", "scope", "sort"].includes(k) && filters[k]).length;
  const inventoryLabel = user.can.see_all_inventory ? "All assets" : `${user.department.code} inventory`;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{scope === "marketplace" ? "Marketplace" : inventoryLabel}</h1>
          <p>
            {scope === "marketplace"
              ? "Surplus items other departments have published for reuse. Check here before buying new."
              : user.can.see_all_inventory ? "Every asset record on campus, in any state."
              : `Assets owned by ${user.department.name}, in any state.`}
          </p>
        </div>
        <div className="btn-row">
          <div className="segmented" role="group" aria-label="What to show">
            <button aria-pressed={scope === "marketplace"} onClick={() => update("scope", "")}>Marketplace</button>
            <button aria-pressed={scope === "inventory"} onClick={() => update("scope", "inventory")}>{inventoryLabel}</button>
          </div>
          {user.can.register_assets && <Link className="btn btn-primary" to="/assets/new">Register asset</Link>}
        </div>
      </div>

      <div className="market">
        <aside className="filters" aria-label="Filters">
          <Field label="Category">
            {(p) => (
              <Select {...p} value={filters.category} onChange={(e) => update("category", e.target.value)}>
                <option value="">Any category</option>
                {meta?.categories.map((c) => <option key={c.name}>{c.name}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Minimum condition">
            {(p) => (
              <Select {...p} value={filters.condition} onChange={(e) => update("condition", e.target.value)}>
                <option value="">Any condition</option>
                {meta?.conditions.map((c) => <option key={c} value={c}>{c} or better</option>)}
              </Select>
            )}
          </Field>
          <Field label="Department">
            {(p) => (
              <Select {...p} value={filters.department_id} onChange={(e) => update("department_id", e.target.value)}>
                <option value="">Any department</option>
                {meta?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Campus">
            {(p) => (
              <Select {...p} value={filters.campus} onChange={(e) => update("campus", e.target.value)}>
                <option value="">Any campus</option>
                {meta && Object.keys(meta.locations).map((c) => <option key={c}>{c}</option>)}
              </Select>
            )}
          </Field>
          {scope === "inventory" && (
            <Field label="Life-cycle status">
              {(p) => (
                <Select {...p} value={filters.status} onChange={(e) => update("status", e.target.value)}>
                  <option value="">Any status</option>
                  {meta?.asset_statuses.map((s) => <option key={s}>{s}</option>)}
                </Select>
              )}
            </Field>
          )}
          <Field label="Quantity at least">
            {(p) => (
              <Input {...p} type="number" min="1" inputMode="numeric" value={filters.min_quantity}
                onChange={(e) => update("min_quantity", e.target.value)} />
            )}
          </Field>
          <Field label="Bought within (years)">
            {(p) => (
              <Input {...p} type="number" min="0" inputMode="numeric" value={filters.max_age_years}
                onChange={(e) => update("max_age_years", e.target.value)} />
            )}
          </Field>
          {user.can.see_value && (
            <Field label="Estimated value (AED)">
              {() => (
                <div style={{ display: "flex", gap: 8 }}>
                  <Input aria-label="Minimum value" placeholder="Min" type="number" min="0" value={filters.min_value}
                    onChange={(e) => update("min_value", e.target.value)} />
                  <Input aria-label="Maximum value" placeholder="Max" type="number" min="0" value={filters.max_value}
                    onChange={(e) => update("max_value", e.target.value)} />
                </div>
              )}
            </Field>
          )}
          {activeFilters > 0 && (
            <button className="btn btn-quiet btn-sm" style={{ marginTop: 14 }} onClick={clear}>
              Clear {activeFilters} filter{activeFilters > 1 ? "s" : ""}
            </button>
          )}
        </aside>

        <section>
          <div className="searchbar">
            <Icon name="search" />
            <label htmlFor="asset-search" className="sr-only">Search assets</label>
            <input id="asset-search" className="input" type="search" placeholder="Search by name, description or tag"
              value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="results-head">
            <span className="muted small" aria-live="polite">
              {loading ? "Searching…" : data ? `${data.total} ${data.total === 1 ? "item" : "items"}` : ""}
            </span>
            <label className="small muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              Sort by
              <select className="input" style={{ height: 32, width: "auto", fontSize: 13.5 }} value={filters.sort || "relevance"}
                onChange={(e) => update("sort", e.target.value === "relevance" ? "" : e.target.value)}>
                <option value="relevance">Relevance</option>
                <option value="newest">Newest</option>
                <option value="condition">Best condition</option>
                <option value="nearest">Nearest to me</option>
                <option value="name">Name</option>
              </select>
            </label>
          </div>

          {error && <ErrorState error={error} onRetry={reload} />}
          <div className="panel">
            {loading && !data ? <LoadingRows rows={5} /> : data && data.items.length === 0 ? (
              <Empty title="No matching assets"
                action={user.can.submit_requests && (
                  <Link className="btn btn-primary" to={`/requests/new${filters.category ? `?category=${encodeURIComponent(filters.category)}` : ""}`}>
                    Submit a request
                  </Link>
                )}>
                {user.can.submit_requests
                  ? "Try fewer filters, or submit a request and you will be told when a matching item is published."
                  : "Try a different keyword or fewer filters."}
              </Empty>
            ) : data && (
              <ul className="list">
                {data.items.map((a) => (
                  <li key={a.id}>
                    <Link to={`/assets/${a.id}`} className="row asset-row">
                      <CategoryGlyph category={a.category} />
                      <div style={{ minWidth: 0 }}>
                        <div className="row-title">{a.name}</div>
                        <div className="row-meta">
                          {a.subcategory || a.category}, {a.department.name}, {a.campus}
                        </div>
                      </div>
                      <div className="row-side">
                        <span className="num">{a.quantity} {a.quantity === 1 ? "unit" : "units"}</span>
                        <span>{a.condition}</span>
                        {user.can.see_value && a.estimated_value != null && <span className="num">{aed(a.estimated_value)}</span>}
                        {scope === "inventory" && <Status value={a.status} />}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
