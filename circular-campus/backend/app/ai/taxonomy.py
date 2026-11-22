"""Standard category list shared by the UI, the classifier and the matcher.

Each subcategory carries the keywords the local classifier looks for, a typical
material, the details a good listing should include (for missing-information
prompts, FR-AI-3) and a rough typical weight per unit. The weight is used only
as a tie-breaker that favours more waste diversion (FR-AI-8). It is an
estimate, not an agreed factor, because the factor table is still TBD-1.
"""
from __future__ import annotations

from typing import Optional

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Subcategory:
    name: str
    keywords: tuple[str, ...]
    material: str
    weight_kg: float
    expected_details: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Category:
    name: str
    subcategories: tuple[Subcategory, ...]


TAXONOMY: tuple[Category, ...] = (
    Category("IT Equipment", (
        Subcategory("Laptop", ("laptop", "notebook", "macbook", "thinkpad", "latitude", "elitebook", "ultrabook",
                               "chromebook"), "Aluminium / plastic", 2.0, ("brand", "model", "processor", "ram", "storage")),
        Subcategory("Desktop Computer", ("desktop", "pc", "workstation", "tower", "imac", "optiplex", "all-in-one"),
                    "Steel / plastic", 8.0, ("brand", "model", "processor", "ram", "storage")),
        Subcategory("Monitor", ("monitor", "display", "screen", "lcd", "led display"), "Plastic / glass", 5.0,
                    ("brand", "screen size")),
        Subcategory("Printer", ("printer", "laserjet", "inkjet", "multifunction", "copier", "plotter"),
                    "Plastic / steel", 15.0, ("brand", "model")),
        Subcategory("Networking", ("router", "switch", "access point", "modem", "firewall", "ethernet", "wifi"),
                    "Steel / plastic", 3.0, ("brand", "model")),
        Subcategory("Tablet", ("tablet", "ipad", "galaxy tab", "surface go"), "Aluminium / glass", 0.6,
                    ("brand", "model", "storage")),
        Subcategory("Peripherals", ("keyboard", "mouse", "webcam", "docking", "dock", "headset", "hard drive",
                                    "ssd", "usb hub", "scanner"), "Plastic", 0.5, ("brand",)),
        Subcategory("Server", ("server", "rack", "nas", "storage array"), "Steel", 25.0,
                    ("brand", "model", "processor", "ram", "storage")),
    )),
    Category("Audio-Visual", (
        Subcategory("Projector", ("projector", "beamer", "lumens"), "Plastic / glass", 3.5, ("brand", "model")),
        Subcategory("Screen / Display Panel", ("projection screen", "smart board", "interactive display",
                                               "tv", "television", "smartboard"), "Aluminium / glass", 20.0,
                    ("brand", "screen size")),
        Subcategory("Camera", ("camera", "camcorder", "dslr", "tripod", "lens"), "Plastic / metal", 1.0,
                    ("brand", "model")),
        Subcategory("Audio Equipment", ("speaker", "microphone", "mixer", "amplifier", "pa system", "soundbar"),
                    "Plastic / metal", 4.0, ("brand", "model")),
    )),
    Category("Furniture", (
        Subcategory("Chair", ("chair", "chairs", "seat", "seating", "stool", "armchair", "ergonomic"),
                    "Steel frame / fabric", 9.0, ("colour", "material")),
        Subcategory("Desk / Table", ("desk", "table", "workbench", "workstation desk", "standing desk"),
                    "Wood / steel", 30.0, ("dimensions", "material")),
        Subcategory("Storage Cabinet", ("cabinet", "locker", "filing", "drawer", "cupboard", "wardrobe"),
                    "Steel", 35.0, ("dimensions", "material")),
        Subcategory("Shelving", ("shelf", "shelves", "shelving", "bookcase", "rack unit"), "Steel / wood", 20.0,
                    ("dimensions", "material")),
        Subcategory("Whiteboard", ("whiteboard", "white board", "notice board", "pinboard", "flipchart"),
                    "Aluminium / melamine", 10.0, ("dimensions",)),
        Subcategory("Sofa / Lounge", ("sofa", "couch", "bench", "lounge", "beanbag"), "Wood / fabric", 40.0,
                    ("colour", "material")),
    )),
    Category("Laboratory Equipment", (
        Subcategory("Measurement Instrument", ("oscilloscope", "multimeter", "signal generator", "spectrum analyzer",
                                               "power supply", "function generator", "logic analyzer"),
                    "Steel / plastic", 6.0, ("brand", "model", "calibration date")),
        Subcategory("Microscope / Optics", ("microscope", "spectrometer", "telescope", "optical", "magnifier"),
                    "Metal / glass", 8.0, ("brand", "model")),
        Subcategory("Lab Apparatus", ("centrifuge", "incubator", "fume hood", "beaker", "pipette", "hot plate",
                                      "balance", "scale", "autoclave", "3d printer",
                                      "soldering", "arduino", "raspberry pi", "breadboard"),
                    "Steel / glass", 12.0, ("brand", "model", "safety notes")),
        Subcategory("Safety Equipment", ("goggles", "safety", "first aid", "fire extinguisher", "lab coat",
                                         "gloves", "eyewash"), "Mixed", 2.0, ("expiry date",)),
    )),
    Category("Books & Learning Materials", (
        Subcategory("Textbook", ("textbook", "book", "books", "edition", "handbook", "manual", "isbn"), "Paper", 1.0,
                    ("title", "edition")),
        Subcategory("Teaching Kit", ("kit", "model kit", "teaching aid", "lego", "educational", "flashcards"),
                    "Mixed", 3.0, ("contents list",)),
    )),
    Category("Office Equipment", (
        Subcategory("Shredder / Laminator", ("shredder", "laminator", "binding machine", "guillotine"),
                    "Plastic / steel", 8.0, ("brand", "model")),
        Subcategory("Appliance", ("fridge", "refrigerator", "microwave", "kettle", "coffee machine",
                                  "water dispenser", "fan", "heater"), "Steel / plastic", 20.0, ("brand", "model")),
        Subcategory("Phone / Communication", ("phone", "telephone", "ip phone", "conference phone", "walkie"),
                    "Plastic", 0.8, ("brand", "model")),
        Subcategory("Stationery", ("stationery", "stapler", "paper", "folders", "binders", "toner", "cartridge",
                                   "markers"), "Paper / plastic", 1.0, ("quantity per pack",)),
    )),
    Category("Other", (
        Subcategory("Miscellaneous", (), "Mixed", 5.0, ()),
    )),
)

CATEGORY_NAMES: tuple[str, ...] = tuple(c.name for c in TAXONOMY)


def find_category(name: Optional[str]) -> Optional[Category]:
    if not name:
        return None
    for c in TAXONOMY:
        if c.name.lower() == name.strip().lower():
            return c
    return None


def find_subcategory(category: Optional[str], sub: Optional[str]) -> Optional[Subcategory]:
    cat = find_category(category)
    if not cat or not sub:
        return None
    for s in cat.subcategories:
        if s.name.lower() == sub.strip().lower():
            return s
    return None


def typical_weight(category: Optional[str], sub: Optional[str]) -> float:
    s = find_subcategory(category, sub)
    if s:
        return s.weight_kg
    cat = find_category(category)
    if cat and cat.subcategories:
        return sum(x.weight_kg for x in cat.subcategories) / len(cat.subcategories)
    return 5.0


def taxonomy_as_dict() -> list[dict]:
    return [{"name": c.name, "subcategories": [s.name for s in c.subcategories]} for c in TAXONOMY]


KNOWN_BRANDS = (
    "Dell", "HP", "Lenovo", "Apple", "Asus", "Acer", "Microsoft", "Samsung", "LG", "Sony", "Epson", "BenQ",
    "Canon", "Nikon", "Brother", "Xerox", "Cisco", "Ubiquiti", "Netgear", "Logitech", "Bose", "JBL", "Shure",
    "Herman Miller", "Steelcase", "IKEA", "Haworth", "Humanscale", "Keysight", "Tektronix", "Rigol", "Fluke",
    "Olympus", "Zeiss", "Leica", "Thermo Fisher", "Eppendorf", "Prusa", "Ultimaker", "Raspberry Pi", "Arduino",
    "Panasonic", "Philips", "ViewSonic", "Optoma", "Synology", "Fellowes", "Polycom", "Yealink", "Pearson",
    "Wiley", "Springer", "O'Reilly",
)

MATERIAL_WORDS = {
    "wood": "Wood", "wooden": "Wood", "oak": "Wood", "beech": "Wood", "mdf": "Engineered wood (MDF)",
    "steel": "Steel", "metal": "Metal", "aluminium": "Aluminium", "aluminum": "Aluminium", "iron": "Iron",
    "plastic": "Plastic", "polypropylene": "Plastic", "glass": "Glass", "fabric": "Fabric", "mesh": "Mesh",
    "leather": "Leather", "laminate": "Laminate", "melamine": "Melamine",
}
