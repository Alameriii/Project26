import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button, Field, Input, Notice } from "../components/ui.jsx";
import { useSession } from "../lib/session.jsx";

// Demo accounts for the prototype only (fictional people, shared password).
// Remove this list before any real deployment.
const DEMO_PASSWORD = "demo1234";
const DEMO = [
  ["Yousef Ali", "yousef.ali@campus.test", "Requester, Computer Science"],
  ["Hamad Saeed", "hamad.saeed@campus.test", "Asset Custodian, Electrical Eng."],
  ["Fatima Noor", "fatima.noor@campus.test", "Dept. Representative, Electrical Eng."],
  ["Sara Mansour", "sara.mansour@campus.test", "Asset Custodian, Computer Science"],
  ["Omar Khalid", "omar.khalid@campus.test", "Dept. Representative, Computer Science"],
  ["Dana Karim", "dana.karim@campus.test", "Sustainability Officer"],
  ["Layla Haddad", "admin@campus.test", "System Administrator"],
];

function BigLoop() {
  return (
    <svg className="big-loop" width="420" height="420" viewBox="0 0 420 420" fill="none" aria-hidden="true">
      <circle cx="210" cy="210" r="170" stroke="#34584a" strokeWidth="38" />
      <path d="M380 210a170 170 0 1 1-68-136" stroke="#7fb59e" strokeWidth="38" strokeLinecap="round" />
    </svg>
  );
}

export default function LoginPage() {
  const { user, login, signedOutReason } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={location.state?.from || "/"} replace />;

  const submit = async (e) => {
    e.preventDefault();
    const fe = {};
    if (!email.trim()) fe.email = "Enter your university email.";
    if (!password) fe.password = "Enter your password.";
    setFieldErrors(fe);
    if (Object.keys(fe).length) return;
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <section className="auth-art">
        <div>
          <h1>Give campus equipment a second life.</h1>
          <p>
            Find surplus furniture, computers and lab equipment from other departments before buying new,
            and track every item as it moves across campus.
          </p>
        </div>
        <p className="small" style={{ color: "#8fae9e" }}>COSC 336 prototype, Phase 6</p>
        <BigLoop />
      </section>
      <section className="auth-form">
        <div className="auth-card">
          <h2>Sign in</h2>
          <p className="muted" style={{ marginBottom: 24 }}>Use your university email and password.</p>
          {signedOutReason && !error && <div style={{ marginBottom: 16 }}><Notice tone="info">{signedOutReason}</Notice></div>}
          {error && <div style={{ marginBottom: 16 }}><Notice tone="error">{error}</Notice></div>}
          <form onSubmit={submit} noValidate className="stack">
            <Field label="Email" error={fieldErrors.email}>
              {(p) => (
                <Input {...p} type="email" autoComplete="username" value={email}
                  onChange={(e) => setEmail(e.target.value)} />
              )}
            </Field>
            <Field label="Password" error={fieldErrors.password}>
              {(p) => (
                <Input {...p} type="password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} />
              )}
            </Field>
            <Button variant="primary" className="btn-block" type="submit" loading={busy}>Sign in</Button>
          </form>
          <details className="demo-list">
            <summary>Demo accounts (password {DEMO_PASSWORD})</summary>
            <div style={{ marginTop: 10 }}>
              {DEMO.map(([name, mail, role]) => (
                <button key={mail} type="button" className="demo-btn"
                  onClick={() => { setEmail(mail); setPassword(DEMO_PASSWORD); setError(null); }}>
                  <span>{name}</span>
                  <span>{role}</span>
                </button>
              ))}
            </div>
          </details>
        </div>
      </section>
    </div>
  );
}
