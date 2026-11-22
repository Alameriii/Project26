// Small fetch wrapper. The session lives in an httpOnly cookie set by the server;
// no tokens or API keys are ever stored in the browser.

export class ApiError extends Error {
  constructor(message, status, fields = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

async function request(method, path, body) {
  const opts = {
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json", "X-Requested-With": "fetch" },
  };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`/api${path}`, opts);
  } catch {
    throw new ApiError("Cannot reach the server. Check that the backend is running.", 0);
  }
  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/auth/login")) onUnauthorized(data?.detail);
    throw new ApiError(data?.detail || `Request failed (${res.status}).`, res.status, data?.fields || {});
  }
  return data;
}

export const api = {
  get: (path, params) => {
    const qs = params
      ? "?" +
        new URLSearchParams(
          Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
        ).toString()
      : "";
    return request("GET", path + (qs === "?" ? "" : qs));
  },
  post: (path, body = {}) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
};
