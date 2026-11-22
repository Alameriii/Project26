# Circular Campus

**Intelligent, AI-Powered Circular Campus Resource Exchange and Asset Life Cycle Management System**
COSC 336, Fall 2026, Phase 6 draft implementation.

Departments register assets and publish surplus items. Other departments search for them, request them and
track their requests. The owning department approves or rejects each request, and approved transfers are
recorded until the receiver confirms receipt. Every step is kept in the asset's history. Two AI features
support people but never make the decision: asset classification and resource matching.

---

## Quick start

Requirements: Python 3.9 or newer, and Node.js 18+.

```bash
# 1. Backend dependencies
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Build the interface
cd ../frontend
npm install
npm run build

# 3. Run (serves the interface and the API together)
cd ../backend
python -m uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000. On first start the database is created and loaded with demo data.
On macOS/Linux, `./run.sh` from the project folder does steps 2 and 3.

**Windows "Could not install packages due to an OSError" / "WinError 2":** Python is installed in a folder you
cannot write to (for example `C:\Python39`). Install into your user folder instead:
`python -m pip install --user -r requirements.txt`

**Development mode** (hot reload): run the backend with `uvicorn app.main:app --reload --port 8000`, and in
`frontend/` run `npm run dev`. Then open http://localhost:5173. Vite forwards `/api` to the backend.

**Reset the demo data:** `cd backend && python -m app.seed --reset`

**Run the checks:** `cd backend && python -m pytest -q`

### Using PostgreSQL (the target database from Phases 2–3)

Without settings, the app uses a local SQLite file so it runs with zero setup. To use PostgreSQL, create a
database and set `DATABASE_URL` in `backend/.env` (copy `backend/.env.example`):

```
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/circular_campus
```

Tables are created automatically on start. The checks were run on SQLite and PostgreSQL 16. To run them on
PostgreSQL, set `TEST_DATABASE_URL`. The test run drops and recreates every table in that database, so point
it at a separate test database.

### Connecting the AI service (optional)

Put `GEMINI_API_KEY=...` in `backend/.env`. The key is read only by the backend; it is never sent to the browser
and must not be committed. Without a key, both AI features use a **local rule-based fallback**, and the interface
says so wherever suggestions appear.

> Status: the Gemini integration is implemented and checked against mocked API responses, but it has **not
> been tested against the live Gemini service**: no key was available while building. Confirm it with a real key
> before relying on it. If the service fails, times out after 10 s or returns invalid output, the app falls back
> automatically and shows "AI ranking is unavailable".

---

## Demo accounts

All passwords are `demo1234`. People and the `campus.test` domain are fictional. The sign-in page lists these
accounts so you can fill them in with one click. Remove that list before any real use.

| Name | Email | Role | Department |
|---|---|---|---|
| Yousef Ali | yousef.ali@campus.test | Requester | Computer Science |
| Sara Mansour | sara.mansour@campus.test | Asset Custodian | Computer Science |
| Omar Khalid | omar.khalid@campus.test | Department Representative (approver) | Computer Science |
| Hamad Saeed | hamad.saeed@campus.test | Asset Custodian | Electrical Engineering |
| Fatima Noor | fatima.noor@campus.test | Department Representative (approver) | Electrical Engineering |
| Mariam Ahmed | mariam.ahmed@campus.test | Requester | Electrical Engineering |
| Khalid Rashed | khalid.rashed@campus.test | Department Representative | Mechanical Engineering |
| Noura Salem | noura.salem@campus.test | Asset Custodian | Mechanical Engineering |
| Reem Yousef | reem.yousef@campus.test | Department Representative + Custodian | Library Services |
| Saif Mubarak | saif.mubarak@campus.test | Department Representative | Student Affairs |
| Hessa Obaid | hessa.obaid@campus.test | Requester | Student Affairs |
| Bilal Aziz | bilal.aziz@campus.test | Asset Custodian | Facilities & Procurement |
| Dana Karim | dana.karim@campus.test | Sustainability Officer (view only in Phase 6) | Facilities & Procurement |
| Layla Haddad | admin@campus.test | System Administrator | Facilities & Procurement |

The demo data includes 21 asset records across six departments, one completed exchange, one request waiting for Omar
Khalid's decision, and one open request with no suitable item yet.

### Demonstration script (about 5 minutes)

1. **Hamad Saeed** → Marketplace → *Register asset*. Name "Dell 27-inch 4K monitors", description
   "Dell U2720Q 4K USB-C monitors, small scratch on one stand". Choose *Suggest category and tags*, then
   *Use these details*. Set quantity 4, tick *Publish as surplus now*, and choose *Register asset*.
2. **Yousef Ali** → Marketplace, search "screen" (synonyms find monitors). Then *New request*: IT Equipment,
   quantity 2, purpose "Second screens for the TA room", specifications "27 inch display". Choose
   *Find matches*, pick the top match and choose *Request selected item*. The item is reserved for 3 working days.
3. **Fatima Noor** → Approvals → *Approve*. She picks a method and date, and a transfer is scheduled. Yousef
   cannot approve his own request, and Hamad (a custodian) cannot approve at all.
4. **Hamad Saeed** → Transfers → open the transfer → *Mark dispatched*.
5. **Sara Mansour** → Transfers → *Confirm receipt* (condition, avoided purchase).
6. Open the asset. Its owner is now Computer Science, its custodian Sara and its status In Use. The history
   shows who did what and when, from registration to receipt.

---

## What is implemented

| Phase 6 item | Where | Notes |
|---|---|---|
| **C1** Login and roles | `security/auth.py`, `security/permissions.py` | Email + password (bcrypt), httpOnly session cookie, 30-min idle sign-out, lock after 5 wrong passwords for 15 min. Every API call checks role and department on the server (Phase 3 §2.3). |
| **C2** Asset registration and management | `services/assets.py`, *Register asset*, asset page | Name, description, category, subcategory, tags, material, quantity, department, custodian, location, purchase date, value (AED), condition, status. Unique IDs (`AST-0001`). Edits keep old values in history. |
| **C3** Publish, search and filter | `services/search.py`, Marketplace | Publish/withdraw. Keyword search over name, tags and description, with synonyms. Filters: category, minimum condition, department, campus, status, quantity, age, value. Sort by relevance, newest, condition, nearest or name. Value is hidden from requesters (FR-SRC-5). "No matching assets" offers a request. |
| **C4** Requests and reservations | `services/requests.py`, New request, My requests | Request a listed item or a described need. Reservation for 3 working days (expires automatically), first-come waiting list, cancel before approval, open requests for later matching. |
| **C5** Review, approval and transfers | `services/approvals.py`, `services/transfers.py` | Only the owning department's representative or an admin decides. No self-approval. A rejection needs a reason, and the requester is offered up to 3 alternatives. Approval creates a Scheduled transfer. The sender dispatches; the receiving custodian confirms; then department, custodian, location and status change. A partial quantity is split into its own asset record. Report a problem (Disputed) or cancel while Scheduled. A transfer cannot exist before approval. The last item cannot go to two people: row locking plus one reservation per asset, checked with concurrent requests on PostgreSQL. |
| **C6** States and history | `domain/lifecycle.py`, history timelines | Asset, request and transfer state machines from Phase 3 §2.4. Any other move is rejected. Every action is recorded with the user and the time; split-off records include their parent's history. Append-only audit log for admins. |
| **AI 1** Classification | `ai/classifier.py` | Suggests category, subcategory, up to 8 tags, material, standard description, likely condition, missing details, confidence and a reason. Below 0.6 the suggestion is labelled "Low confidence". The user accepts, edits or dismisses, and the decision is logged. |
| **AI 2** Matching | `ai/matcher.py` | Hard rules first. Then a 0–1 score from meaning, category, condition, location, timing and repair need, shown out of 100. Top 5, each with a confidence and a 2–3-factor reason. Ties favour more waste diverted. The match list and the user's choice are logged. |
| C8 Notifications (partial) | bell menu | In-app messages for new, approved, rejected, expired and dispatched requests and transfers, plus new listings that score 75+ for an open request. |
| Administration | Administration page | Create/deactivate users, add departments, search the audit log. |

**AI never approves or authorises anything.** Classification only fills the form when the user chooses *Use these
details*. Matching only ranks items, and the owning department still approves. Both are logged with model
version, input summary, output, confidence and the user's decision (FR-AUD-4).

### How the matching score works

```
relevance    = 0.70 × meaning + 0.30 × category
practicality = 0.30 × condition + 0.30 × location + 0.20 × timing + 0.20 × repair need
score        = relevance × (0.6 + 0.4 × practicality)        (0–1, shown out of 100)
```

Relevance gates the score, so a nearby item in good condition cannot rank highly when it is not what was asked
for. Scores under 0.40 are not shown. "Meaning" comes from Gemini embeddings when configured, and otherwise
from local TF-IDF keyword similarity with synonyms. Before scoring, hard rules remove items that are not
Available, have too few units, are below the minimum condition, belong to the requester's own department, or
whose listing has ended.

---

## Project structure

```
backend/
  app/
    main.py              FastAPI app, error handling, serves the built interface
    config.py            settings from environment / backend/.env
    database.py          SQLAlchemy engine (SQLite by default, PostgreSQL via DATABASE_URL)
    models.py            Department, User, Asset, ResourceRequest, MatchRecommendation, Transfer,
                         HistoryEvent, AuditLog, AIRecommendationLog, Notification, UserSession
    domain/              enums, life-cycle state machines, campus locations
    security/            passwords, sessions, PermissionPolicy
    services/            AssetService, AssetSearchService, RequestService, MatchService,
                         ApprovalService, TransferService, AuditService, serializers
    ai/                  taxonomy, ClassificationService, MatchingEngine, GeminiClient
    api/                 routes and validated request schemas
    seed.py              demo data
  tests/test_phase6_flow.py   implementation checks (flow, permissions, life cycle, AI fallback)
frontend/
  src/pages/             Login, Home, Marketplace, Asset detail/form, Requests, Approvals, Transfers, Admin
  src/components/        layout, shared UI, match list, decision dialogs
```

The classes follow the Phase 4–5 design. Asset, ResourceRequest and Transfer have their own state machines.
MatchRecommendation links a request to a recommended asset with score, explanation and model version. The
backend layers match the Level-1 DFD processes: 1.0 log in, 2.0 asset records, 3.0 requests, 4.0 transfers.

---

## Conflicts between documents, and assumptions

Where documents disagreed, I followed the most specific requirement:

- **Roles.** The Phase 6 slides require at least requester, custodian and approver/admin. Phase 3 lists nine
  actors. This build has Requester, Asset Custodian, Department Representative (the approver), System
  Administrator and Sustainability Officer, who can view all inventory but has no workflow yet. Maintenance
  Staff and Procurement/Finance belong to later modules.
- **Score scale.** The Phase 6 slide example shows "score 91", while FR-AI-6 says 0–1. Scores are stored 0–1
  and shown out of 100.
- **Request states.** Phase 3 §2.4 lists *Draft*, but UC-6 uses *Open* for a need with no item chosen. This
  build implements Open and does not use Draft. It adds two moves the table does not list:
  - Submitted → Open, when a queued request's item goes to someone else.
  - Approved → Cancelled, when a Scheduled transfer is cancelled.
- **Transfer states.** Received and Completed are recorded together when the receiver confirms.
- **"Implement at least 2 and 5 AI features."** Read as "at least 2 of the 5". This build implements
  classification and matching, as the Phases 6–8 plan says.
- **Receiving custodian.** The requester when they are a custodian. Otherwise the first custodian in their
  department, then the department representative, then the requester.
- **Own department.** Users cannot request their own department's assets; such items are left out of matches.
- **Working days.** Monday to Friday, for the 3-day reservation.
- **Category list and weights.** Sample values. The per-category weights are rough estimates used only to
  break ties, because the agreed factor table is still TBD-1 in Phase 3.

## Known limitations (to address next)

- Gemini has not been tested live (see above). With the fallback, matching is keyword-based. It handles synonyms
  in its list, but not meaning in general.
- The sanity checks on the classifier and matcher used a handful of examples written for this build. They are
  not the Phase 7 evaluation (10 assets, 20 requests).
- Not in this draft:
  - photos and documents (FR-AST-3);
  - email copies of notifications (FR-NOT-2);
  - maintenance and end-of-life workflows (UC-10/11), hazardous-item checks (NFR-6) and the
    high-value second approval (FR-APR-6);
  - the sustainability dashboard (C7), CSV reports (C9), the assistant and generated reports (AI 3–5).
- Disputed transfers are recorded and announced, but resolving them needs a future admin workflow; the asset
  stays In Transfer.
- Expiry is checked whenever request or asset data is loaded, not by a background job.
- The development server uses HTTP. Serve over HTTPS in deployment (NFR-9) and set `COOKIE_SECURE=true`.
- Search filtering runs partly in Python, which is fine for a prototype but should move fully into SQL for
  large inventories.
