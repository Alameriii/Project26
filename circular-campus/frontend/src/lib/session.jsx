import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, setUnauthorizedHandler } from "./api.js";

const SessionContext = createContext(null);
const ToastContext = createContext(() => {});

export function SessionProvider({ children }) {
  const [user, setUser] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [signedOutReason, setSignedOutReason] = useState(null);

  const loadMeta = useCallback(async () => {
    const m = await api.get("/meta");
    setMeta(m);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler((reason) => {
      setUser(null);
      setMeta(null);
      setSignedOutReason(reason || "Please sign in again.");
    });
    (async () => {
      try {
        const { user } = await api.get("/auth/me");
        setUser(user);
        await loadMeta();
      } catch {
        setUser(null);
        setSignedOutReason(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [loadMeta]);

  const login = useCallback(
    async (email, password) => {
      const { user } = await api.post("/auth/login", { email, password });
      setSignedOutReason(null);
      setUser(user);
      await loadMeta();
      return user;
    },
    [loadMeta]
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setUser(null);
      setMeta(null);
      setSignedOutReason(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, meta, loading, login, logout, signedOutReason, reloadMeta: loadMeta }),
    [user, meta, loading, login, logout, signedOutReason, loadMeta]
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return useContext(SessionContext);
}

export function hasRole(user, ...roles) {
  return !!user && roles.some((r) => user.roles.includes(r));
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);
  const push = useCallback((message, tone = "ok") => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone === "error" ? "error" : ""}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
