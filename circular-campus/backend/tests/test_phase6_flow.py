"""Phase 6 implementation checks (basic verification, not the Phase 7 test report).

Covers the demonstration flow end to end through the HTTP API, the main
permission rules, the life-cycle guards and the AI fallback.
Run from the backend folder:  python -m pytest -q
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.pop("GEMINI_API_KEY", None)
os.environ["FRONTEND_DIST"] = os.path.join(_tmp, "no-dist")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

PW = "demo1234"
H = {"X-Requested-With": "fetch"}
SOON = (date.today() + timedelta(days=7)).isoformat()


@pytest.fixture(scope="module")
def server():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


def client_for(server_client: TestClient, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    c.headers.update(H)
    return c


def asset_payload(**kw):
    base = dict(name="Dell 27-inch monitor", description="Dell U2720Q 27-inch 4K monitor, small scratch",
                category="IT Equipment", subcategory="Monitor", tags=["monitor", "dell"], quantity=4,
                campus="Main Campus", building="Engineering Building", room="E2-120",
                purchase_date="2024-01-10", estimated_value=1200, condition="Good", publish_now=True)
    base.update(kw)
    return base


def request_payload(**kw):
    base = dict(category="IT Equipment", purpose="Second screens for teaching assistants",
                specifications="24 inch or larger monitor", quantity=2, preferred_condition="Fair",
                urgency="Medium", delivery_campus="Main Campus", delivery_building="Engineering Building",
                delivery_room="C1-030", required_date=SOON)
    base.update(kw)
    return base


def test_login_and_lockout(server):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "yousef.ali@campus.test", "password": "wrong"}).status_code == 401
    assert c.get("/api/auth/me").status_code == 401
    for _ in range(5):
        r = c.post("/api/auth/login", json={"email": "bilal.aziz@campus.test", "password": "nope"})
    assert "locked" in r.json()["detail"]
    r = c.post("/api/auth/login", json={"email": "bilal.aziz@campus.test", "password": PW})
    assert r.status_code == 401 and "locked" in r.json()["detail"]


def test_csrf_header_required(server):
    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "hamad.saeed@campus.test", "password": PW})
    assert c.post("/api/assets", json=asset_payload()).status_code == 403


def test_full_demo_flow(server):
    hamad = client_for(server, "hamad.saeed@campus.test")      # EE custodian
    fatima = client_for(server, "fatima.noor@campus.test")     # EE representative
    yousef = client_for(server, "yousef.ali@campus.test")      # CS requester
    sara = client_for(server, "sara.mansour@campus.test")      # CS custodian

    # 1. AI classification (local fallback, clearly labelled)
    r = hamad.post("/api/ai/classify", json={"name": "Dell 27-inch monitor", "description": "small scratch"})
    assert r.status_code == 200
    s = r.json()
    assert s["suggestion"]["category"] == "IT Equipment" and s["suggestion"]["subcategory"] == "Monitor"
    assert s["suggestion"]["provider"] == "local-fallback" and "local keyword rules" in s["notice"]
    assert 0 <= s["suggestion"]["confidence"] <= 1

    # 2. Register + publish
    r = hamad.post("/api/assets", json=asset_payload(ai_log_id=s["log_id"], ai_decision="accepted"))
    assert r.status_code == 201, r.text
    asset = r.json()["asset"]
    assert asset["status"] == "Available" and asset["asset_code"].startswith("AST-")

    # 3. Search (requester cannot see value)
    r = yousef.get("/api/assets", params={"q": "screen", "category": "IT Equipment"})
    items = r.json()["items"]
    assert any(i["id"] == asset["id"] for i in items)
    assert all("estimated_value" not in i for i in items)

    # 4. AI matching
    r = yousef.post("/api/ai/match", json=request_payload())
    m = r.json()
    assert m["provider"] == "local-fallback" and m["notice"]
    assert 1 <= len(m["matches"]) <= 5
    top = m["matches"][0]
    assert top["asset"]["category"] == "IT Equipment" and 0 <= top["score"] <= 1 and top["reason"]
    assert all(x["asset"]["department"]["name"] != "Computer Science" for x in m["matches"])

    # 5. Submit request for the new asset → reserved
    r = yousef.post("/api/requests", json=request_payload(asset_id=asset["id"], match_log_id=m["log_id"]))
    assert r.status_code == 201, r.text
    req = r.json()["request"]
    assert req["status"] == "Submitted" and req["reserved_until"]
    assert hamad.get(f"/api/assets/{asset['id']}").json()["asset"]["status"] == "Reserved"

    # transfer cannot exist before approval; requester cannot approve
    assert yousef.post(f"/api/requests/{req['id']}/approve",
                       json={"method": "Delivery", "scheduled_date": SOON}).status_code == 403
    # custodian (not representative) cannot approve
    assert hamad.post(f"/api/requests/{req['id']}/approve",
                      json={"method": "Delivery", "scheduled_date": SOON}).status_code == 403

    # 6. Representative reviews and approves (2 of 4 units → split)
    assert fatima.post(f"/api/requests/{req['id']}/start-review").json()["request"]["status"] == "Under Review"
    r = fatima.post(f"/api/requests/{req['id']}/approve", json={"method": "Delivery", "scheduled_date": SOON})
    assert r.status_code == 200, r.text
    t = r.json()["transfer"]
    assert t["status"] == "Scheduled" and t["quantity"] == 2
    parent = hamad.get(f"/api/assets/{asset['id']}").json()["asset"]
    assert parent["status"] == "Available" and parent["quantity"] == 2

    # receiver cannot confirm before dispatch; requester cannot dispatch
    assert sara.post(f"/api/transfers/{t['id']}/confirm",
                     json={"condition_on_arrival": "Good", "avoided_purchase": True}).status_code == 409
    assert yousef.post(f"/api/transfers/{t['id']}/dispatch", json={}).status_code == 403

    # 7. Dispatch and confirm receipt
    r = hamad.post(f"/api/transfers/{t['id']}/dispatch", json={"handover_note": "Boxed"})
    assert r.json()["transfer"]["status"] == "Dispatched"
    assert hamad.post(f"/api/transfers/{t['id']}/confirm",
                      json={"condition_on_arrival": "Good", "avoided_purchase": True}).status_code == 403
    r = sara.post(f"/api/transfers/{t['id']}/confirm",
                  json={"condition_on_arrival": "Good", "avoided_purchase": True, "note": "All good"})
    assert r.status_code == 200, r.text
    assert r.json()["transfer"]["status"] == "Completed"

    # 8. Updated owner, status and history
    moved = sara.get(f"/api/assets/{t['asset']['id']}").json()
    assert moved["asset"]["status"] == "In Use"
    assert moved["asset"]["department"]["name"] == "Computer Science"
    assert moved["asset"]["custodian"]["name"] == "Sara Mansour"
    actions = [h["action"] for h in moved["history"]]
    assert {"Ownership transferred", "Dispatched", "Transfer approved", "Split from parent"} <= set(actions)
    assert all(h["user"] or h["action"] in ("Reservation released",) for h in moved["history"])
    rq = yousef.get(f"/api/requests/{req['id']}").json()["request"]
    assert rq["status"] == "Fulfilled" and rq["recommendations"]


def test_permissions_and_rules(server):
    yousef = client_for(server, "yousef.ali@campus.test")
    omar = client_for(server, "omar.khalid@campus.test")       # CS representative
    reem = client_for(server, "reem.yousef@campus.test")       # LIB rep + custodian
    fatima = client_for(server, "fatima.noor@campus.test")

    # Requester cannot register assets, use classification, or reach admin pages
    assert yousef.post("/api/assets", json=asset_payload()).status_code == 403
    assert yousef.post("/api/ai/classify", json={"name": "chair"}).status_code == 403
    assert yousef.get("/api/admin/users").status_code == 403
    assert yousef.get("/api/admin/audit").status_code == 403
    assert yousef.get("/api/requests", params={"scope": "approvals"}).status_code == 403

    # Representative cannot register for another department
    other = omar.get("/api/meta").json()["departments"]
    ee = next(d for d in other if d["code"] == "EE")
    assert omar.post("/api/assets", json=asset_payload(department_id=ee["id"])).status_code == 403

    # Cannot edit another department's asset
    items = omar.get("/api/assets", params={"q": "bookshelves"}).json()["items"]
    shelf = items[0]
    body = {k: shelf[k] for k in ("name", "description", "category", "subcategory", "tags", "material",
                                   "quantity", "campus", "building", "room", "purchase_date", "condition")}
    assert omar.put(f"/api/assets/{shelf['id']}", json=body).status_code == 403

    # Self-approval is blocked (BR-3): Reem (LIB rep) requests an EE asset, then
    # an admin-free check — Reem cannot approve it because it is her own request.
    eeasset = next(i for i in reem.get("/api/assets", params={"q": "oscilloscope"}).json()["items"])
    r = reem.post("/api/requests", json=request_payload(category="Laboratory Equipment", purpose="Lab demo",
                                                        quantity=1, asset_id=eeasset["id"]))
    rid = r.json()["request"]["id"]
    assert reem.post(f"/api/requests/{rid}/approve",
                     json={"method": "Delivery", "scheduled_date": SOON}).status_code == 403

    # Last item cannot go to two people: a second request queues; it cannot be approved first
    r2 = yousef.post("/api/requests", json=request_payload(category="Laboratory Equipment", purpose="Scope",
                                                           quantity=1, asset_id=eeasset["id"]))
    req2 = r2.json()["request"]
    assert req2["queued"] is True and req2["status"] == "Submitted"
    assert fatima.post(f"/api/requests/{req2['id']}/approve",
                       json={"method": "Delivery", "scheduled_date": SOON}).status_code == 409

    # Rejecting the first hands the reservation to the queued request
    r = fatima.post(f"/api/requests/{rid}/reject", json={"reason": "Needed for exams"})
    assert r.status_code == 200
    again = yousef.get(f"/api/requests/{req2['id']}").json()["request"]
    assert again["queued"] is False and again["reserved_until"]

    # Rejection requires a reason
    assert fatima.post(f"/api/requests/{req2['id']}/reject", json={"reason": ""}).status_code == 422

    # Invalid life-cycle moves are blocked
    eeitems = fatima.get("/api/assets", params={"scope": "inventory", "q": "soldering"}).json()["items"]
    sold = eeitems[0]
    r = fatima.post(f"/api/assets/{sold['id']}/status", json={"to_status": "Donated"})
    assert r.status_code == 409 and "cannot move" in r.json()["detail"]
    r = fatima.post(f"/api/assets/{sold['id']}/status", json={"to_status": "In Transfer"})
    assert r.status_code == 409

    # Requesting your own department's asset is refused
    cs_item = omar.get("/api/assets", params={"q": "thinkpad"}).json()["items"][0]
    assert yousef.post("/api/requests", json=request_payload(asset_id=cs_item["id"], quantity=1)).status_code == 422

    # Validation errors come back per field
    r = fatima.post("/api/assets", json=asset_payload(name="", quantity=0, estimated_value=-5))
    assert r.status_code == 422 and {"name", "quantity", "estimated_value"} <= set(r.json()["fields"])


def test_admin_audit_and_users(server):
    admin = client_for(server, "admin@campus.test")
    r = admin.get("/api/admin/audit")
    assert r.status_code == 200 and any(i["action"] == "request_approved" for i in r.json()["items"])
    r = admin.post("/api/admin/users", json={"name": "New Person", "email": "new.person@campus.test",
                                             "password": "longpassword", "department_id": 1,
                                             "roles": ["requester"]})
    assert r.status_code == 201
    uid = r.json()["user"]["id"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"active": False}).json()["user"]["active"] is False
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "new.person@campus.test", "password": "longpassword"})
    assert r.status_code == 401 and "deactivated" in r.json()["detail"]


def test_view_only_role_and_reservation_expiry(server):
    dana = client_for(server, "dana.karim@campus.test")         # Sustainability Officer
    me = dana.get("/api/auth/me").json()["user"]
    assert me["can"]["submit_requests"] is False and me["can"]["see_all_inventory"] is True
    inv = dana.get("/api/assets", params={"scope": "inventory"}).json()["items"]
    assert {i["department"]["name"] for i in inv} >= {"Computer Science", "Electrical Engineering"}
    assert dana.post("/api/ai/match", json=request_payload()).status_code == 403
    assert dana.post("/api/requests", json=request_payload(asset_id=inv[0]["id"])).status_code == 403

    # A reservation older than 3 working days expires and the asset is released (BR-7)
    hessa = client_for(server, "hessa.obaid@campus.test")
    item = hessa.get("/api/assets", params={"q": "workbench"}).json()["items"][0]
    r = hessa.post("/api/requests", json=request_payload(category="Furniture", purpose="Bench for club", quantity=1,
                                                         asset_id=item["id"])).json()["request"]
    from datetime import datetime, timezone

    from app.database import SessionLocal
    from app.models import ResourceRequest
    with SessionLocal() as db:
        db.get(ResourceRequest, r["id"]).reserved_until = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.commit()
    again = hessa.get(f"/api/requests/{r['id']}").json()["request"]
    assert again["status"] == "Expired"
    assert hessa.get(f"/api/assets/{item['id']}").json()["asset"]["status"] == "Available"


def test_ai_fallback_when_service_fails(monkeypatch):
    """With a key configured but the service unreachable, results fall back and say so."""
    from app.ai.classifier import ClassificationService
    from app.ai.gemini import GeminiClient

    client = GeminiClient(api_key="invalid-test-key", timeout=0.5)

    def boom(*a, **k):
        from app.ai.gemini import AIServiceUnavailable
        raise AIServiceUnavailable("AI service could not be reached (test).")

    monkeypatch.setattr(client, "_post", boom)
    result, reason = ClassificationService(client).classify("Office chair", "mesh, black")
    assert result.provider == "local-fallback" and result.subcategory == "Chair" and "test" in reason

    from types import SimpleNamespace

    from app.ai.matcher import MatchingEngine, MatchSpec
    from app.domain.enums import AssetStatus, Condition, Urgency

    def stub(i, name, cat, sub, cond=Condition.GOOD, status=AssetStatus.AVAILABLE, qty=5):
        return SimpleNamespace(id=i, name=name, category=cat, subcategory=sub, description=name, tags=[],
                               status=status, department_id=1, quantity=qty, condition=cond,
                               available_until=None, campus="Main Campus", building="Student Centre")

    pool = [stub(1, "Mesh office chair", "Furniture", "Chair"), stub(2, "Oak desk", "Furniture", "Desk / Table"),
            stub(3, "Broken chair", "Furniture", "Chair", cond=Condition.POOR),
            stub(4, "Reserved chair", "Furniture", "Chair", status=AssetStatus.RESERVED),
            stub(5, "Two chairs", "Furniture", "Chair", qty=2)]
    spec = MatchSpec("Furniture", "Need 4 chairs for a lab", "", 4, Condition.FAIR, Urgency.LOW, "Main Campus",
                     "Student Centre", date.today(), requester_department_id=999)
    outcome = MatchingEngine(client).match(spec, pool, date.today())
    assert outcome.provider == "local-fallback" and "unavailable" in outcome.notice
    assert [r.asset_id for r in outcome.results] == [1]   # hard rules removed 3, 4, 5; the desk is not relevant
    assert outcome.excluded == {"condition below minimum": 1, "not available": 1, "quantity too low": 1,
                                "low relevance": 1}
    assert 0 < outcome.results[0].score <= 1 and "chair" in outcome.results[0].reason


def test_gemini_path_with_mocked_http(monkeypatch):
    """Checks request/response handling for the Gemini provider with fake HTTP replies.
    This does NOT prove a live Gemini connection; no key is used."""
    import json as _json
    from types import SimpleNamespace

    import httpx

    from app.ai.classifier import ClassificationService
    from app.ai.gemini import GeminiClient
    from app.ai.matcher import MatchingEngine, MatchSpec
    from app.domain.enums import AssetStatus, Condition, Urgency

    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append((url, headers))
        if ":generateContent" in url:
            text = _json.dumps({"category": "Furniture", "subcategory": "Chair", "tags": ["chair", "mesh"],
                                "material": "Mesh", "standard_description": "Mesh office chair.",
                                "suggested_condition": "Good", "missing_information": ["Add the colour."],
                                "confidence": 0.91, "reason": "It is a chair."})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})
        n = len(json["requests"])
        vecs = [[1.0, 0.0]] + [[0.9, 0.1], [0.1, 0.9]][: n - 1]
        return httpx.Response(200, json={"embeddings": [{"values": v} for v in vecs]})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiClient(api_key="test-key-not-real", model="test-model", embedding_model="test-embed")
    result, fallback = ClassificationService(client).classify("Office chair", "mesh")
    assert fallback is None and result.provider == "gemini" and result.subcategory == "Chair"
    assert calls[0][1]["x-goog-api-key"] == "test-key-not-real"   # key travels in a header, server-side only

    def stub(i, name):
        return SimpleNamespace(id=i, name=name, category="Furniture", subcategory="Chair", description=name, tags=[],
                               status=AssetStatus.AVAILABLE, department_id=1, quantity=5, condition=Condition.GOOD,
                               available_until=None, campus="Main Campus", building="Student Centre")

    spec = MatchSpec("Furniture", "Need chairs", "", 2, Condition.FAIR, Urgency.LOW, "Main Campus", "Student Centre",
                     date.today(), requester_department_id=999)
    outcome = MatchingEngine(client).match(spec, [stub(1, "Mesh chair"), stub(2, "Odd chair")], date.today())
    assert outcome.provider == "gemini" and outcome.notice is None
    assert outcome.results[0].asset_id == 1

    # Invalid category from the AI → validated and rejected → local fallback
    def bad_post(url, json=None, timeout=None, headers=None):
        text = _json.dumps({"category": "Spaceships", "subcategory": "Rocket", "confidence": 0.99})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})
    monkeypatch.setattr(httpx, "post", bad_post)
    result, fallback = ClassificationService(client).classify("Office chair", "mesh")
    assert result.provider == "local-fallback" and "outside the standard list" in fallback
