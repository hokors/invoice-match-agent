"""Field-by-field scoring of an extraction against the answer key's `printed` section."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

HEADER_FIELDS = ["supplier_name", "supplier_tin", "invoice_number", "invoice_date", "po_number"]
LINE_FIELDS = ["supplier_code", "description", "quantity", "unit", "unit_price", "line_total"]
MONEY_FIELDS = ["subtotal", "vat", "total"]


def _norm_text(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def _norm_id(v) -> str:
    """Invoice/PO/TIN/code comparison: ignore case, spaces and a leading 'No.' label."""
    s = re.sub(r"^\s*(no\.?|#)\s*", "", str(v or ""), flags=re.I)
    return re.sub(r"\s+", "", s).upper()


def _num_eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 0.005


def field_ok(field: str, got, want) -> bool:
    if field in ("quantity", "unit_price", "line_total", *MONEY_FIELDS):
        return _num_eq(got, want)
    if field in ("supplier_tin",):
        return re.sub(r"\D", "", str(got or "")) == re.sub(r"\D", "", str(want or ""))
    if field in ("invoice_number", "po_number", "supplier_code"):
        return _norm_id(got) == _norm_id(want)
    if field == "description":
        return SequenceMatcher(None, _norm_text(got), _norm_text(want)).ratio() >= 0.9
    return _norm_text(got) == _norm_text(want)


def score_invoice(got: dict, want: dict) -> dict:
    """Returns {field: (correct, total)} plus a list of human-readable mistakes."""
    counts: dict[str, list[int]] = {}
    mistakes: list[str] = []

    def tally(field, ok, detail):
        c = counts.setdefault(field, [0, 0])
        c[0] += ok
        c[1] += 1
        if not ok:
            mistakes.append(detail)

    for f in HEADER_FIELDS + MONEY_FIELDS:
        tally(f, field_ok(f, got.get(f), want.get(f)), f"{f}: expected {want.get(f)!r}, got {got.get(f)!r}")

    g_lines, w_lines = got.get("lines") or [], want.get("lines") or []
    tally("line_count", len(g_lines) == len(w_lines), f"line_count: expected {len(w_lines)}, got {len(g_lines)}")
    for i, w in enumerate(w_lines):
        g = g_lines[i] if i < len(g_lines) else {}
        for f in LINE_FIELDS:
            tally(f"line.{f}", field_ok(f, g.get(f), w.get(f)), f"lines[{i}].{f}: expected {w.get(f)!r}, got {g.get(f)!r}")

    numbers_ok = all(not m.startswith(("subtotal", "vat", "total")) and ".quantity" not in m
                     and ".unit_price" not in m and ".line_total" not in m and not m.startswith("line_count")
                     for m in mistakes)
    return {"counts": counts, "mistakes": mistakes, "all_ok": not mistakes, "numbers_ok": numbers_ok}
