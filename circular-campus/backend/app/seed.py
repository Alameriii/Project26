"""Sample data for the demo (Phase 3 assumption: representative sample data is acceptable).

All names and the campus.test email domain are fictional. Seeding goes through
the same services as the app, so the sample history and audit entries are real.
Run `python -m app.seed --reset` to rebuild the demo database.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .api.schemas import ApproveIn, AssetCreate, ConfirmIn, RequestCreate
from .database import Base, SessionLocal, engine, init_db
from .domain.enums import AssetStatus, Condition, Role, TransferMethod, Urgency
from .models import Department, User
from .security.passwords import hash_password
from .timeutil import today

DEMO_PASSWORD = "demo1234"

DEPARTMENTS = [
    ("CS", "Computer Science", "Main Campus", "Engineering Building"),
    ("EE", "Electrical Engineering", "Main Campus", "Engineering Building"),
    ("ME", "Mechanical Engineering", "SAN Campus", "Research Complex"),
    ("LIB", "Library Services", "Main Campus", "Library & Learning Commons"),
    ("SA", "Student Affairs", "Main Campus", "Student Centre"),
    ("FAC", "Facilities & Procurement", "Main Campus", "Administration Building"),
]

USERS = [
    # name, email, dept, roles
    ("Layla Haddad", "admin@campus.test", "FAC", [Role.ADMIN]),
    ("Dana Karim", "dana.karim@campus.test", "FAC", [Role.SUSTAINABILITY]),
    ("Bilal Aziz", "bilal.aziz@campus.test", "FAC", [Role.CUSTODIAN]),
    ("Omar Khalid", "omar.khalid@campus.test", "CS", [Role.DEPT_REP]),
    ("Sara Mansour", "sara.mansour@campus.test", "CS", [Role.CUSTODIAN]),
    ("Yousef Ali", "yousef.ali@campus.test", "CS", [Role.REQUESTER]),
    ("Fatima Noor", "fatima.noor@campus.test", "EE", [Role.DEPT_REP]),
    ("Hamad Saeed", "hamad.saeed@campus.test", "EE", [Role.CUSTODIAN]),
    ("Mariam Ahmed", "mariam.ahmed@campus.test", "EE", [Role.REQUESTER]),
    ("Khalid Rashed", "khalid.rashed@campus.test", "ME", [Role.DEPT_REP]),
    ("Noura Salem", "noura.salem@campus.test", "ME", [Role.CUSTODIAN]),
    ("Reem Yousef", "reem.yousef@campus.test", "LIB", [Role.DEPT_REP, Role.CUSTODIAN]),
    ("Saif Mubarak", "saif.mubarak@campus.test", "SA", [Role.DEPT_REP]),
    ("Hessa Obaid", "hessa.obaid@campus.test", "SA", [Role.REQUESTER]),
]


def _d(days_ago: int) -> date:
    return today() - timedelta(days=days_ago)


# custodian email, name, description, category, subcategory, tags, material, qty, building, room,
# purchased days ago, value AED, condition, target status, availability note
ASSETS = [
    # Electrical Engineering — surplus IT and lab equipment
    ("hamad.saeed", "Dell 24-inch monitor", "Dell P2422H 24-inch IPS monitor with height-adjustable stand. "
     "Small scratch on one bezel, otherwise works well.", "IT Equipment", "Monitor",
     ["monitor", "dell", "24-inch", "ips", "height-adjustable"], "Plastic / glass", 6, "Engineering Building",
     "E2-114", 1300, 750, Condition.GOOD, AssetStatus.AVAILABLE, "Left over after the lab upgrade; collect from E2-114."),
    ("hamad.saeed", "Rigol 4-channel oscilloscope", "Rigol DS1054Z digital oscilloscope, 50 MHz, 4 channels, "
     "with probes. Calibrated last year.", "Laboratory Equipment", "Measurement Instrument",
     ["oscilloscope", "rigol", "50 mhz", "4-channel"], "Steel / plastic", 2, "Engineering Building", "E2-210",
     1700, 1900, Condition.GOOD, AssetStatus.AVAILABLE, "Spare units from the circuits teaching lab."),
    ("hamad.saeed", "Bench power supply", "Dual-output 30 V / 5 A DC bench power supply.", "Laboratory Equipment",
     "Measurement Instrument", ["power supply", "dc", "30v"], "Steel", 4, "Engineering Building", "E2-210",
     2200, 650, Condition.FAIR, AssetStatus.AVAILABLE, None),
    ("hamad.saeed", "HP LaserJet printer", "HP LaserJet Pro M404dn, duplex, network ready. Toner half full.",
     "IT Equipment", "Printer", ["printer", "hp", "laser", "duplex"], "Plastic / steel", 1, "Engineering Building",
     "E2-101", 1500, 1100, Condition.GOOD, AssetStatus.AVAILABLE, None),
    ("hamad.saeed", "Soldering stations", "Temperature-controlled soldering stations, 60 W.", "Laboratory Equipment",
     "Lab Apparatus", ["soldering", "60w"], "Plastic / steel", 8, "Engineering Building", "E2-212", 900, 300,
     Condition.GOOD, AssetStatus.IN_USE, None),

    # Computer Science
    ("sara.mansour", "Lenovo ThinkPad T14 laptop", "Lenovo ThinkPad T14 Gen 2, Core i5, 16GB RAM, 512GB SSD, "
     "Windows 11. Battery holds about 5 hours.", "IT Equipment", "Laptop",
     ["laptop", "lenovo", "core i5", "16gb ram", "512gb ssd", "windows 11"], "Aluminium / plastic", 3,
     "Engineering Building", "C1-020", 1100, 3200, Condition.GOOD, AssetStatus.AVAILABLE,
     "Returned staff laptops, wiped and reimaged."),
    ("sara.mansour", "Epson classroom projector", "Epson EB-X41 3600 lumens XGA projector with remote and ceiling "
     "mount.", "Audio-Visual", "Projector", ["projector", "epson", "3600 lumens"], "Plastic / glass", 1,
     "Engineering Building", "C1-105", 2000, 1800, Condition.FAIR, AssetStatus.AVAILABLE, None),
    ("sara.mansour", "Dell OptiPlex desktop", "Dell OptiPlex 7080, Core i7, 16GB RAM, 256GB SSD.", "IT Equipment",
     "Desktop Computer", ["desktop", "dell", "core i7", "16gb ram"], "Steel / plastic", 10, "Engineering Building",
     "C1-210", 1400, 2800, Condition.GOOD, AssetStatus.IN_USE, None),
    ("sara.mansour", "Raspberry Pi 4 kits", "Raspberry Pi 4 Model B 4GB with case, power supply and SD card.",
     "Laboratory Equipment", "Lab Apparatus", ["raspberry pi", "kit", "4gb"], "Plastic", 15,
     "Engineering Building", "C1-020", 700, 280, Condition.NEW, AssetStatus.REGISTERED, None),

    # Mechanical Engineering (SAN Campus)
    ("noura.salem", "Ergonomic mesh office chair", "Ergonomic mesh office chairs with adjustable lumbar support "
     "and armrests. Light wear on some armrests.", "Furniture", "Chair",
     ["chair", "ergonomic", "mesh", "adjustable"], "Steel frame / mesh", 12, "Research Complex", "R-118",
     1800, 650, Condition.GOOD, AssetStatus.AVAILABLE, "Office refit surplus. Collection from SAN Campus."),
    ("noura.salem", "Steel workbench", "Heavy-duty steel workbench, 180 x 75 cm, with a drawer.", "Furniture",
     "Desk / Table", ["workbench", "steel", "180 x 75 cm"], "Steel", 3, "Research Complex", "R-020", 2600, 1500,
     Condition.FAIR, AssetStatus.AVAILABLE, None),
    ("noura.salem", "Prusa 3D printer", "Prusa i3 MK3S+ 3D printer. Nozzle needs replacing; prints otherwise.",
     "Laboratory Equipment", "Lab Apparatus", ["3d printer", "prusa"], "Steel / plastic", 1, "Research Complex",
     "R-130", 1600, 3500, Condition.POOR, AssetStatus.UNDER_MAINTENANCE, None),
    ("noura.salem", "Mobile whiteboard", "Double-sided mobile whiteboard on wheels, 120 x 90 cm.", "Furniture",
     "Whiteboard", ["whiteboard", "mobile", "double-sided"], "Aluminium / melamine", 2, "Research Complex", "R-101",
     1200, 450, Condition.GOOD, AssetStatus.AVAILABLE, None),

    # Library Services
    ("reem.yousef", "Wooden study tables", "Oak study tables for four people, 160 x 80 cm.", "Furniture",
     "Desk / Table", ["desk", "table", "wood", "study"], "Wood", 6, "Library & Learning Commons", "L-G12", 3000,
     900, Condition.GOOD, AssetStatus.AVAILABLE, "Replaced by new group-study furniture."),
    ("reem.yousef", "Steel bookshelves", "Five-tier steel bookshelves, 90 cm wide.", "Furniture", "Shelving",
     ["shelf", "steel", "five-tier"], "Steel", 10, "Library & Learning Commons", "L-B02", 3500, 400,
     Condition.FAIR, AssetStatus.AVAILABLE, None),
    ("reem.yousef", "Calculus textbooks", "Stewart, Calculus: Early Transcendentals, 8th edition. Light pencil "
     "notes.", "Books & Learning Materials", "Textbook", ["textbook", "calculus", "8th edition"], "Paper", 25,
     "Library & Learning Commons", "L-B10", 2500, 120, Condition.FAIR, AssetStatus.AVAILABLE, None),
    ("reem.yousef", "iPad tablets", "Apple iPad 9th generation, 64GB, Wi-Fi, with cases.", "IT Equipment", "Tablet",
     ["tablet", "ipad", "apple", "64gb"], "Aluminium / glass", 8, "Library & Learning Commons", "L-101", 800,
     1300, Condition.GOOD, AssetStatus.IN_USE, None),

    # Student Affairs / Facilities
    ("saif.mubarak", "Folding event chairs", "Black plastic folding chairs for events.", "Furniture", "Chair",
     ["chair", "folding", "event"], "Plastic", 40, "Student Centre", "S-001", 1000, 60, Condition.FAIR,
     AssetStatus.IN_USE, None),
    ("bilal.aziz", "Conference speakerphone", "Polycom conference phone with expansion microphones.", "Office Equipment",
     "Phone / Communication", ["conference phone", "polycom", "microphone"], "Plastic", 2, "Administration Building",
     "A-204", 2100, 900, Condition.GOOD, AssetStatus.AVAILABLE, None),
    ("bilal.aziz", "Steel filing cabinets", "Four-drawer steel filing cabinets with keys.", "Furniture",
     "Storage Cabinet", ["cabinet", "filing", "steel", "lockable"], "Steel", 5, "Administration Building", "A-B01",
     3200, 700, Condition.GOOD, AssetStatus.AVAILABLE, "Archive move; keys included."),
]


def _users_by_handle(db: Session) -> dict[str, User]:
    users = db.scalars(select(User)).all()
    return {u.email.split("@")[0]: u for u in users}


def seed(db: Session) -> None:
    from .services.approvals import ApprovalService
    from .services.assets import AssetService
    from .services.requests import RequestService
    from .services.transfers import TransferService

    depts = {}
    for code, name, campus, building in DEPARTMENTS:
        d = Department(code=code, name=name, campus=campus, building=building)
        db.add(d)
        depts[code] = d
    db.flush()
    for name, email, dept, roles in USERS:
        u = User(name=name, email=email, password_hash=hash_password(DEMO_PASSWORD),
                 department_id=depts[dept].id, roles_csv="")
        u.roles = roles
        db.add(u)
    db.commit()

    users = _users_by_handle(db)
    assets_svc = AssetService(db)
    created = {}
    for (handle, name, desc, cat, sub, tags, material, qty, building, room, age, value, cond, status,
         note) in ASSETS:
        owner = users[handle]
        data = AssetCreate(name=name, description=desc, category=cat, subcategory=sub, tags=tags,
                           material=material, quantity=qty, campus=owner.department.campus, building=building,
                           room=room, purchase_date=_d(age), estimated_value=value, condition=cond,
                           publish_now=status == AssetStatus.AVAILABLE, availability_note=note,
                           custodian_id=owner.id)
        actor = owner
        asset = assets_svc.register(actor, data)
        if status in (AssetStatus.IN_USE, AssetStatus.UNDER_MAINTENANCE):
            assets_svc.change_status(actor, asset, AssetStatus.IN_USE, "Allocated to the department")
        if status == AssetStatus.UNDER_MAINTENANCE:
            assets_svc.change_status(actor, asset, AssetStatus.UNDER_MAINTENANCE, "Nozzle replacement booked")
        created[name] = asset

    # A completed exchange, so the history and transfer pages are not empty.
    req_svc = RequestService(db)
    hessa, khalid, noura, saif = users["hessa.obaid"], users["khalid.rashed"], users["noura.salem"], users["saif.mubarak"]
    wb = created["Mobile whiteboard"]
    r1 = req_svc.create(hessa, RequestCreate(
        category="Furniture", purpose="Whiteboard for student club planning sessions",
        specifications="Mobile, double-sided preferred", quantity=1, preferred_condition=Condition.FAIR,
        urgency=Urgency.MEDIUM, delivery_campus="Main Campus", delivery_building="Student Centre",
        delivery_room="S-014", required_date=today() + timedelta(days=7), asset_id=wb.id))
    t1 = ApprovalService(db).approve(khalid, r1, ApproveIn(method=TransferMethod.DELIVERY,
                                                           scheduled_date=today(), note="Happy to help."))
    tsvc = TransferService(db)
    tsvc.dispatch(noura, t1, "Delivered by the facilities van.")
    tsvc.confirm(saif, t1, ConfirmIn(condition_on_arrival=Condition.GOOD, avoided_purchase=True,
                                     note="Received in good condition."))

    # A request waiting for the Computer Science representative (Omar Khalid).
    mariam = users["mariam.ahmed"]
    req_svc.create(mariam, RequestCreate(
        category="Audio-Visual", purpose="Projector for the EE seminar room",
        specifications="At least 3000 lumens, ceiling mount", quantity=1, preferred_condition=Condition.FAIR,
        urgency=Urgency.HIGH, delivery_campus="Main Campus", delivery_building="Engineering Building",
        delivery_room="E1-005", required_date=today() + timedelta(days=5),
        asset_id=created["Epson classroom projector"].id))

    # An open request with no suitable listing yet.
    req_svc.create(hessa, RequestCreate(
        category="Office Equipment", purpose="Microwave for the student lounge kitchen",
        specifications="Countertop, at least 20 litres", quantity=1, preferred_condition=Condition.GOOD,
        urgency=Urgency.LOW, delivery_campus="Main Campus", delivery_building="Student Centre",
        required_date=today() + timedelta(days=30), save_as_open=True))
    db.commit()


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(User.id).limit(1)) is not None:
        return False
    seed(db)
    return True


def reset() -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
        print("Database reset and demo data loaded.")
    else:
        init_db()
        with SessionLocal() as db:
            print("Demo data loaded." if seed_if_empty(db) else "Database already has data; use --reset to rebuild.")
