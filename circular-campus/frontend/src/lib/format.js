const STATUS_TONE = {
  // assets
  Registered: "",
  "In Use": "",
  Available: "green",
  Reserved: "amber",
  "In Transfer": "blue",
  "Under Maintenance": "amber",
  "Pending Disposition": "violet",
  Donated: "",
  Recycled: "",
  Disposed: "",
  // requests
  Open: "",
  Submitted: "blue",
  "Under Review": "violet",
  Approved: "green",
  Rejected: "red",
  Fulfilled: "green",
  Cancelled: "",
  Expired: "",
  // transfers
  Scheduled: "blue",
  Dispatched: "amber",
  Received: "green",
  Completed: "green",
  Disputed: "red",
};

export function statusTone(status) {
  return STATUS_TONE[status] ?? "";
}

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? value + "T00:00:00" : value);
  return Number.isNaN(d.getTime()) ? "—" : dateFmt.format(d);
}

export function fmtDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : dateTimeFmt.format(d);
}

export function relative(value) {
  if (!value) return "";
  const diff = (Date.now() - new Date(value).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return fmtDate(value);
}

export function aed(value) {
  if (value === null || value === undefined) return "—";
  return `AED ${Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function initials(name = "") {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}

export function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export const FACTOR_LABELS = {
  semantic: "Description match",
  category: "Category",
  condition: "Condition",
  location: "Location",
  timing: "Timing",
  repair: "Repair need",
};
