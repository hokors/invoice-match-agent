"""Invoice file -> structured data, using Gemini with a JSON response schema.

The schema lives in schema/invoice.schema.json (JSON Schema). Gemini wants an OpenAPI-style
subset, so it is converted here. The prompt lives in prompts/extract_invoice.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import ROOT
from .gemini import Gemini, GeminiResult

SCHEMA_FILE = ROOT / "schema" / "invoice.schema.json"
PROMPT_FILE = ROOT / "prompts" / "extract_invoice.md"


def to_gemini_schema(node: dict) -> dict:
    """JSON Schema (draft 2020-12 subset) -> Gemini responseSchema."""
    out: dict = {}
    t = node.get("type")
    nullable = False
    if isinstance(t, list):
        nullable = "null" in t
        t = next(x for x in t if x != "null")
    if t:
        out["type"] = t.upper()
    if nullable:
        out["nullable"] = True
    if "description" in node:
        out["description"] = node["description"]
    if "enum" in node:
        out["type"], out["enum"] = "STRING", node["enum"]
    if t == "object":
        out["properties"] = {k: to_gemini_schema(v) for k, v in node.get("properties", {}).items()}
        if node.get("required"):
            out["required"] = node["required"]
        out["propertyOrdering"] = list(node.get("properties", {}))
    if t == "array":
        out["items"] = to_gemini_schema(node["items"])
    return out


def load_schema() -> dict:
    return to_gemini_schema(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))


_NUM = re.compile(r"[^\d.\-]")


def as_number(v):
    if v is None or isinstance(v, (int, float)):
        return v
    s = _NUM.sub("", str(v))
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def normalize(data: dict) -> dict:
    """Light cleanup only: numbers as numbers, trimmed strings, '-' or '' -> None. No correcting of values."""
    def clean_str(v):
        if v is None:
            return None
        v = str(v).strip()
        return None if v in ("", "-", "N/A", "n/a") else v

    out = {k: clean_str(data.get(k)) for k in ("supplier_name", "supplier_tin", "invoice_number", "invoice_date", "po_number")}
    out["currency"] = clean_str(data.get("currency")) or "PHP"
    out["lines"] = [
        {
            "supplier_code": clean_str(l.get("supplier_code")),
            "description": clean_str(l.get("description")) or "",
            "quantity": as_number(l.get("quantity")),
            "unit": clean_str(l.get("unit")),
            "unit_price": as_number(l.get("unit_price")),
            "line_total": as_number(l.get("line_total")),
        }
        for l in data.get("lines") or []
    ]
    for k in ("subtotal", "vat", "total"):
        out[k] = as_number(data.get(k))
    out["unreadable_fields"] = list(data.get("unreadable_fields") or [])
    return out


class Extractor:
    def __init__(self, gemini: Gemini):
        self.gemini = gemini
        self.schema = load_schema()
        self.prompt = PROMPT_FILE.read_text(encoding="utf-8")

    def extract(self, file: Path) -> tuple[dict, GeminiResult]:
        result = self.gemini.extract(file, self.prompt, self.schema)
        return normalize(result.data), result
