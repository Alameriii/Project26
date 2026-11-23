import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { initials, relative } from "../lib/format.js";
import { hasRole, useSession } from "../lib/session.jsx";
import { Icon, Logo } from "./ui.jsx";

function useOutside(ref, onOutside, active) {
  useEffect(() => {
    if (!active) return;
    const h = (e) => ref.current && !ref.current.contains(e.target) && onOutside();
    const k = (e) => e.key === "Escape" && onOutside();
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => {
      document.removeEventListener("mousedown", h);
      document.removeEventListener("keydown", k);
    };
  }, [ref, onOutside, active]);
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ unread: 0, items: [] });
  const ref = useRef(null);
  const location = useLocation();
  useOutside(ref, () => setOpen(false), open);

  const load = () => api.get("/notifications").then(setData).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [location.pathname]);

  const markAll = async () => {
    await api.post("/notifications/read-all");
    load();
  };

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button className="icon-btn" aria-label={`Notifications, ${data.unread} unread`} aria-expanded={open}
        onClick={() => setOpen((o) => !o)}>
        <Icon name="bell" />
        {data.unread > 0 && <span className="dot-badge" />}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Notifications">
          <div className="popover-head">
            <h3>Notifications</h3>
            {data.unread > 0 && (
              <button className="btn btn-quiet btn-sm" onClick={markAll}>Mark all as read</button>
            )}
          </div>
          {data.items.length === 0 ? (
            <p className="muted small" style={{ padding: "8px 10px 14px" }}>
              You will see updates about your requests, approvals and transfers here.
            </p>
          ) : (
            data.items.map((n) => (
              <Link key={n.id} to={n.link || "#"} className={`popover-item ${n.read ? "" : "unread"}`}
                onClick={() => setOpen(false)}>
                <strong style={{ fontWeight: 500 }}>{n.title}</strong>
                <p>{n.body}</p>
                <p className="faint">{relative(n.at)}</p>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, logout, meta } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();
  useOutside(ref, () => setOpen(false), open);
  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button className="user-chip" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{initials(user.name)}</span>
        <span className="user-name">{user.name.split(" ")[0]}</span>
      </button>
      {open && (
        <div className="popover" style={{ width: 280 }}>
          <div style={{ padding: "10px 10px 12px" }}>
            <strong style={{ fontWeight: 600 }}>{user.name}</strong>
            <p className="muted small">{user.email}</p>
            <p className="small" style={{ marginTop: 8 }}>{user.role_labels.join(", ")}</p>
            <p className="muted small">{user.department.name}</p>
            {meta?.ai && <p className="faint small" style={{ marginTop: 8 }}>AI: {meta.ai.label}</p>}
          </div>
          <button className="menu-btn" onClick={async () => { await logout(); navigate("/login"); }}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user } = useSession();
  const [pending, setPending] = useState(0);
  const location = useLocation();
  const approver = hasRole(user, "admin", "dept_rep");

  useEffect(() => {
    if (!approver) return;
    api.get("/requests", { scope: "approvals" })
      .then((d) => setPending(d.items.filter((r) => !r.queued).length))
      .catch(() => {});
  }, [approver, location.pathname]);

  return (
    <>
      <a href="#main" className="sr-only">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand" aria-label="Circular Campus home">
            <Logo />
            <span>Circular Campus</span>
          </Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Home</NavLink>
            <NavLink to="/assets">Marketplace</NavLink>
            {user.can.submit_requests && <NavLink to="/requests">My requests</NavLink>}
            {approver && (
              <NavLink to="/approvals">
                Approvals {pending > 0 && <span className="count">{pending}</span>}
              </NavLink>
            )}
            <NavLink to="/transfers">Transfers</NavLink>
            {user.can.manage_users && <NavLink to="/admin">Administration</NavLink>}
          </nav>
          <div className="topbar-right">
            <Notifications />
            <UserMenu />
          </div>
        </div>
      </header>
      <main id="main">
        <Outlet />
      </main>
    </>
  );
}
