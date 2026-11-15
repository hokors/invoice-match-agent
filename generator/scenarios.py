"""Turns a purchase order into a supplier invoice, optionally with planted errors.

Each scenario returns the invoice as printed plus an answer key describing every planted issue.
Quantities and prices are compared with the PO and goods receipts exactly as the agent should.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .source import Catalog, PoLine, PurchaseOrder

VAT_RATE = 0.12

# Which scenario to plant, and how often (weights). "clean" = a correct invoice.
SCENARIO_WEIGHTS = {
    "clean": 34,
    "over_billed_qty": 12,
    "price_mismatch": 12,
    "unknown_item": 8,
    "missing_po_ref": 6,
    "wrong_po_ref": 5,
    "math_error": 8,
    "not_received": 7,
    "duplicate_invoice": 6,
    "combo": 8,  # two issues on one invoice
}

ISSUES_NEEDING_REVIEW = {
    "over_billed_qty", "price_mismatch", "unknown_item", "missing_po_ref", "wrong_po_ref",
    "math_error", "not_received", "duplicate_invoice",
}


@dataclass
class InvoiceLine:
    code: str | None
    description: str
    qty: float
    unit: str
    unit_price: float
    line_total: float
    sku: str | None  # Lakan SKU this line really is (answer key only, never printed)


@dataclass
class Invoice:
    invoice_id: str
    invoice_number: str
    invoice_date: str
    po_ref_printed: str | None
    supplier_name: str
    supplier_tin: str
    supplier_city: str
    lines: list[InvoiceLine]
    subtotal: float
    vat: float
    total: float
    issues: list[dict] = field(default_factory=list)
    true_po: str | None = None
    scenario: str = "clean"


def money(x: float) -> float:
    return round(x + 1e-9, 2)


def billable_lines(po: PurchaseOrder) -> list[PoLine]:
    return [l for l in po.lines if l.qty_received > 0]


def make_line(l: PoLine, qty: float, price: float | None = None) -> InvoiceLine:
    price = l.price if price is None else price
    return InvoiceLine(l.supplier_code, l.supplier_name, qty, l.unit, price, money(qty * price), l.sku)


def totals(lines: list[InvoiceLine]) -> tuple[float, float, float]:
    subtotal = money(sum(l.line_total for l in lines))
    vat = money(subtotal * VAT_RATE)
    return subtotal, vat, money(subtotal + vat)


class InvoiceFactory:
    def __init__(self, catalog: Catalog, rng: random.Random, set_name: str):
        self.catalog = catalog
        self.rng = rng
        self.set_name = set_name
        self.counter = 0
        self.next_number: dict[int, int] = {}
        self.issued: list[Invoice] = []

    # --- helpers -------------------------------------------------------------
    def _invoice_number(self, po: PurchaseOrder) -> str:
        sup = po.supplier
        n = self.next_number.get(sup.id, 1000 + self.rng.randint(100, 4000) + (0 if self.set_name == "tune" else 20000))
        self.next_number[sup.id] = n + self.rng.randint(1, 37)
        style = sup.id % 4
        year = po.date_order[:4]
        return [f"SI-{year}-{n:05d}", f"INV/{year}/{n}", f"{n:06d}", f"{sup.ref}-{n}"][style]

    def _invoice_date(self, po: PurchaseOrder) -> str:
        base = po.receipt_date or (date.fromisoformat(po.date_order) + timedelta(days=3)).isoformat()
        return (date.fromisoformat(base) + timedelta(days=self.rng.randint(0, 3))).isoformat()

    def _new(self, po: PurchaseOrder, lines: list[InvoiceLine], po_ref: str | None, scenario: str) -> Invoice:
        self.counter += 1
        subtotal, vat, total = totals(lines)
        inv = Invoice(
            invoice_id=f"{self.set_name}-{self.counter:03d}",
            invoice_number=self._invoice_number(po),
            invoice_date=self._invoice_date(po),
            po_ref_printed=po_ref,
            supplier_name=po.supplier.name,
            supplier_tin=po.supplier.vat,
            supplier_city=po.supplier.city,
            lines=lines,
            subtotal=subtotal,
            vat=vat,
            total=total,
            true_po=po.name,
            scenario=scenario,
        )
        return inv

    def _clean_lines(self, po: PurchaseOrder) -> list[InvoiceLine]:
        return [make_line(l, l.qty_received) for l in billable_lines(po)]

    # --- issue planters (mutate a clean invoice) ------------------------------
    def plant_over_billed(self, inv: Invoice, po: PurchaseOrder):
        by_sku = {l.sku: l for l in po.lines}
        on_po = [il for il in inv.lines if il.sku in by_sku]
        short = [il for il in on_po if by_sku[il.sku].qty_received < by_sku[il.sku].qty_ordered]
        if short:  # natural case: supplier bills the full order although only part arrived
            il = self.rng.choice(short)
            il.qty = by_sku[il.sku].qty_ordered
        else:
            il = self.rng.choice(on_po)
            il.qty = il.qty + self.rng.choice([1, 2, 5, 10])
        il.line_total = money(il.qty * il.unit_price)
        inv.issues.append({"type": "over_billed_qty", "sku": il.sku, "billed_qty": il.qty,
                           "received_qty": by_sku[il.sku].qty_received})

    def plant_price_mismatch(self, inv: Invoice, po: PurchaseOrder):
        on_po = {l.sku for l in po.lines}
        il = self.rng.choice([l for l in inv.lines if l.sku in on_po])
        po_price = il.unit_price
        il.unit_price = money(po_price * self.rng.choice([1.05, 1.08, 1.10, 1.15, 1.2]))
        il.line_total = money(il.qty * il.unit_price)
        inv.issues.append({"type": "price_mismatch", "sku": il.sku, "billed_price": il.unit_price, "po_price": po_price})

    def plant_unknown_item(self, inv: Invoice, po: PurchaseOrder):
        on_po = {l.sku for l in po.lines}
        candidates = [p for p in self.catalog.supplier_products[po.supplier.id] if p.sku not in on_po]
        if not candidates:  # supplier's whole range is on the PO: bill a delivery fee instead
            il = InvoiceLine(None, "Delivery charge", 1, "lot", 850.0, 850.0, None)
        else:
            p = self.rng.choice(candidates)
            qty = self.rng.choice([2, 5, 10])
            il = InvoiceLine(p.supplier_code, p.supplier_name, qty, p.unit, p.price, money(qty * p.price), p.sku)
        inv.lines.append(il)
        inv.issues.append({"type": "unknown_item", "description": il.description, "sku": il.sku})

    def plant_missing_po_ref(self, inv: Invoice, po: PurchaseOrder):
        inv.po_ref_printed = None
        inv.issues.append({"type": "missing_po_ref"})

    def plant_wrong_po_ref(self, inv: Invoice, po: PurchaseOrder):
        others = [p for p in self.catalog.pos if p.supplier.id == po.supplier.id and p.name != po.name]
        wrong = self.rng.choice(others).name if others else "P99999"
        inv.po_ref_printed = wrong
        inv.issues.append({"type": "wrong_po_ref", "printed": wrong, "actual": po.name})

    def plant_math_error(self, inv: Invoice, po: PurchaseOrder):
        where = self.rng.choice(["line_total", "vat", "total"])
        if where == "line_total":
            il = self.rng.choice(inv.lines)
            correct = il.line_total
            il.line_total = money(correct + self.rng.choice([-100, 100, 250, 1000, -0.5 * correct]))
            printed = il.line_total
            # supplier's own totals follow the wrong line, as a careless spreadsheet would
            inv.subtotal, inv.vat, inv.total = totals(inv.lines)
            inv.issues.append({"type": "math_error", "where": "line_total", "sku": il.sku,
                               "printed": printed, "correct": money(il.qty * il.unit_price)})
            return
        if where == "vat":
            correct = inv.vat
            inv.vat = money(inv.subtotal * self.rng.choice([0.10, 0.15, 0.13]))
            inv.total = money(inv.subtotal + inv.vat)
            inv.issues.append({"type": "math_error", "where": "vat", "printed": inv.vat, "correct": correct})
            return
        correct = inv.total
        inv.total = money(correct + self.rng.choice([1000, 500, -500, 90]))
        inv.issues.append({"type": "math_error", "where": "total", "printed": inv.total, "correct": correct})

    def _recompute(self, inv: Invoice):
        if not any(i["type"] == "math_error" for i in inv.issues):
            inv.subtotal, inv.vat, inv.total = totals(inv.lines)

    # --- public --------------------------------------------------------------
    def build(self, po: PurchaseOrder, scenario: str) -> Invoice:
        if scenario == "not_received":
            lines = [make_line(l, l.qty_ordered) for l in po.lines]
            inv = self._new(po, lines, po.name, scenario)
            inv.issues.append({"type": "not_received", "po": po.name})
            self.issued.append(inv)
            return inv

        inv = self._new(po, self._clean_lines(po), po.name, scenario)
        planters = {
            "over_billed_qty": self.plant_over_billed,
            "price_mismatch": self.plant_price_mismatch,
            "unknown_item": self.plant_unknown_item,
            "missing_po_ref": self.plant_missing_po_ref,
            "wrong_po_ref": self.plant_wrong_po_ref,
            "math_error": self.plant_math_error,
        }
        if scenario in planters:
            planters[scenario](inv, po)
        elif scenario == "combo":
            first, second = self.rng.sample(["over_billed_qty", "price_mismatch", "unknown_item", "missing_po_ref"], 2)
            planters[first](inv, po)
            planters[second](inv, po)
            inv.scenario = f"combo:{first}+{second}"
        self._recompute(inv)
        self.issued.append(inv)
        return inv

    def duplicate_of(self, original: Invoice) -> Invoice:
        """Same supplier and invoice number re-sent later (often as a different scan)."""
        self.counter += 1
        dup = Invoice(**{**original.__dict__})
        dup.invoice_id = f"{self.set_name}-{self.counter:03d}"
        dup.lines = [InvoiceLine(**l.__dict__) for l in original.lines]
        dup.issues = [i for i in original.issues] + [{"type": "duplicate_invoice", "of": original.invoice_id}]
        dup.scenario = "duplicate_invoice"
        self.issued.append(dup)
        return dup


def expected_status(inv: Invoice) -> str:
    return "needs_review" if any(i["type"] in ISSUES_NEEDING_REVIEW for i in inv.issues) else "ready"
