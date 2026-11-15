"""Loads Lakan's purchase orders, receipts and supplier product names from Odoo."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.odoo import Odoo


@dataclass
class PoLine:
    product_id: int
    sku: str
    lakan_name: str
    supplier_code: str
    supplier_name: str
    unit: str
    qty_ordered: float
    qty_received: float
    price: float


@dataclass
class Supplier:
    id: int
    name: str
    vat: str
    city: str
    ref: str


@dataclass
class PurchaseOrder:
    id: int
    name: str
    supplier: Supplier
    date_order: str  # YYYY-MM-DD
    receipt_status: str  # full | partial | pending
    receipt_date: str | None
    lines: list[PoLine] = field(default_factory=list)


@dataclass
class Catalog:
    """Everything the generator needs, loaded once."""
    pos: list[PurchaseOrder]
    supplier_products: dict[int, list[PoLine]]  # supplier id -> all their products (qty fields unused)


_UNIT_RE = re.compile(r"\((\w+)(?: of \d+)?\)\s*$")


def unit_from_name(name: str) -> str:
    """'Cola 1.5L (case of 12)' -> 'case'; 'Rice 25kg (sack)' -> 'sack'."""
    m = _UNIT_RE.search(name)
    return m.group(1) if m else "pc"


def load_catalog(odoo: Odoo) -> Catalog:
    suppliers = {
        p["id"]: Supplier(p["id"], p["name"], p["vat"] or "", p["city"] or "", p["ref"] or "")
        for p in odoo.search_read("res.partner", [["supplier_rank", ">", 0]], ["name", "vat", "city", "ref"])
    }
    products = {
        p["id"]: p
        for p in odoo.search_read("product.product", [["purchase_ok", "=", True]], ["default_code", "name", "product_tmpl_id"])
    }
    infos = odoo.search_read("product.supplierinfo", [], ["partner_id", "product_tmpl_id", "product_code", "product_name", "price"])
    by_tmpl_supplier = {(i["product_tmpl_id"][0], i["partner_id"][0]): i for i in infos}

    def make_line(product_id: int, supplier_id: int, qty_ordered=0.0, qty_received=0.0, price=None) -> PoLine:
        prod = products[product_id]
        info = by_tmpl_supplier[(prod["product_tmpl_id"][0], supplier_id)]
        return PoLine(
            product_id=product_id,
            sku=prod["default_code"],
            lakan_name=prod["name"],
            supplier_code=info["product_code"],
            supplier_name=info["product_name"],
            unit=unit_from_name(prod["name"]),
            qty_ordered=qty_ordered,
            qty_received=qty_received,
            price=info["price"] if price is None else price,
        )

    supplier_products: dict[int, list[PoLine]] = {}
    for (tmpl_id, sup_id), info in by_tmpl_supplier.items():
        pid = next(pid for pid, p in products.items() if p["product_tmpl_id"][0] == tmpl_id)
        supplier_products.setdefault(sup_id, []).append(make_line(pid, sup_id))

    pickings = odoo.search_read(
        "stock.picking", [["picking_type_code", "=", "incoming"], ["state", "=", "done"]], ["purchase_id", "date_done"]
    )
    receipt_dates: dict[int, str] = {}
    for p in pickings:
        if p["purchase_id"]:
            po_id = p["purchase_id"][0]
            receipt_dates[po_id] = max(receipt_dates.get(po_id, ""), p["date_done"][:10])

    pos = []
    raw_pos = odoo.search_read(
        "purchase.order", [["state", "=", "purchase"]], ["name", "partner_id", "date_order", "receipt_status"], order="id asc"
    )
    raw_lines = odoo.search_read(
        "purchase.order.line",
        [["order_id", "in", [p["id"] for p in raw_pos]]],
        ["order_id", "product_id", "product_qty", "qty_received", "price_unit"],
        order="id asc",
    )
    for p in raw_pos:
        sup_id = p["partner_id"][0]
        po = PurchaseOrder(
            id=p["id"],
            name=p["name"],
            supplier=suppliers[sup_id],
            date_order=p["date_order"][:10],
            receipt_status=p["receipt_status"],
            receipt_date=receipt_dates.get(p["id"]),
        )
        po.lines = [
            make_line(l["product_id"][0], sup_id, l["product_qty"], l["qty_received"], l["price_unit"])
            for l in raw_lines
            if l["order_id"][0] == p["id"]
        ]
        pos.append(po)
    return Catalog(pos=pos, supplier_products=supplier_products)
