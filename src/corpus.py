"""Loaders for the plain-text corpus in data/docs (listings, clients, banks)."""
import re
from functools import lru_cache
from pathlib import Path

from . import settings


def parse_doc(path: Path) -> dict:
    """Header = 'Key: value' lines up to the first blank line; the rest is the free-text body."""
    text = path.read_text(encoding="utf-8")
    head, _, body = text.partition("\n\n")
    meta = {}
    for line in head.splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    meta["_body"] = body.strip()
    meta["_text"] = text.strip()
    return meta


def _int(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s))


@lru_cache(maxsize=1)
def load_listings() -> dict[str, dict]:
    out = {}
    for p in sorted(settings.DOCS_DIR.glob("LST-*.txt")):
        d = parse_doc(p)
        out[d["ID"]] = {
            "id": d["ID"], "title": d["Title"], "district": d["District"], "compound": d.get("Compound", ""),
            "property_type": d["PropertyType"], "bedrooms": int(d["Bedrooms"]), "bathrooms": int(d["Bathrooms"]),
            "size_sqm": int(d["SizeSqm"]), "price_egp": _int(d["PriceEGP"]), "finishing": d["Finishing"],
            "description": d["Description"],
        }
    return out


@lru_cache(maxsize=1)
def load_clients() -> dict[str, dict]:
    out = {}
    for p in sorted(settings.DOCS_DIR.glob("CLT-*.txt")):
        d = parse_doc(p)
        out[d["ID"]] = {"id": d["ID"], "name": d["Name"], "arabic_name": d["ArabicName"],
                        "language": d["Language"], "districts": d["PreferredDistricts"],
                        "budget": d["BudgetEGP"], "school": d["SchoolRequirement"]}
    return out


@lru_cache(maxsize=1)
def load_banks() -> list[dict]:
    out = []
    for p in sorted(settings.DOCS_DIR.glob("MORT-*.txt")):
        d = parse_doc(p)
        out.append({"id": d["ID"], "bank": d["Bank"], "rate": float(d["AnnualRatePct"]),
                    "max_tenure": int(d["MaxTenureYears"]), "min_down": float(d["MinDownPaymentPct"])})
    return out


def all_doc_ids() -> set[str]:
    return {p.stem for p in settings.DOCS_DIR.glob("*.txt")}
