"""Everything the matcher needs from Odoo, loaded once per run (a few API calls, not one per invoice)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .odoo import Odoo


def norm_code(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


@dataclass
class SupplierProduct:
    product_id: int
    sku: str
    name: str            # Lakan's name
    supplier_code: str   # supplier's code, e.g. PBT-CL15-12
    supplier_name: str   # supplier's name for it, e.g. "Cola Litro 1.5L x12"
    price: float


@dataclass
class PoLine:
    product_id: int
    sku: str
    qty_ordered: float
    qty_received: float
    qty_invoiced: float
    price: float


@dataclass
class PurchaseOrder:
    id: int
    name: str
    supplier_id: int
    date_order: str
    lines: dict[int, PoLine] = field(default_factory=dict)  # product_id -> line

    @property
    def received_anything(self) -> bool:
        return any(l.qty_received > 0 for l in self.lines.values())


@dataclass
class Supplier:
    id: int
    name: str
    tin: str
    products: list[SupplierProduct] = field(default_factory=list)
    pos: list[PurchaseOrder] = field(default_factory=list)


class OdooContext:
    def __init__(self, odoo: Odoo):
        self.odoo = odoo
        self.suppliers: dict[int, Supplier] = {}
        self.pos_by_name: dict[str, PurchaseOrder] = {}
        self.billed_refs: set[tuple[int, str]] = set()  # (supplier id, normalized invoice number) already in Odoo
        self.load()

    def load(self):
        o = self.odoo
        for p in o.search_read("res.partner", [["supplier_rank", ">", 0]], ["name", "vat"]):
            self.suppliers[p["id"]] = Supplier(p["id"], p["name"], digits(p["vat"]))

        variants = {p["product_tmpl_id"][0]: p for p in o.search_read("product.product", [], ["default_code", "name", "product_tmpl_id"])}
        for i in o.search_read("product.supplierinfo", [], ["partner_id", "product_tmpl_id", "product_code", "product_name", "price"]):
            sup = self.suppliers.get(i["partner_id"][0])
            prod = variants.get(i["product_tmpl_id"][0])
            if sup and prod:
                sup.products.append(SupplierProduct(prod["id"], prod["default_code"], prod["name"],
                                                    i["product_code"] or "", i["product_name"] or "", i["price"]))

        pos = o.search_read("purchase.order", [["state", "=", "purchase"]], ["name", "partner_id", "date_order"])
        by_id = {}
        for p in pos:
            po = PurchaseOrder(p["id"], p["name"], p["partner_id"][0], p["date_order"][:10])
            by_id[po.id] = po
            self.pos_by_name[norm_code(po.name)] = po
            if po.supplier_id in self.suppliers:
                self.suppliers[po.supplier_id].pos.append(po)
        sku_of = {p["id"]: p["default_code"] for p in variants.values()}
        for l in o.search_read("purchase.order.line", [["order_id", "in", list(by_id)]],
                               ["order_id", "product_id", "product_qty", "qty_received", "qty_invoiced", "price_unit"]):
            po = by_id[l["order_id"][0]]
            pid = l["product_id"][0]
            po.lines[pid] = PoLine(pid, sku_of.get(pid, ""), l["product_qty"], l["qty_received"], l["qty_invoiced"], l["price_unit"])

        for b in o.search_read("account.move", [["move_type", "=", "in_invoice"], ["state", "!=", "cancel"]], ["partner_id", "ref"]):
            if b["partner_id"] and b["ref"]:
                self.billed_refs.add((b["partner_id"][0], norm_code(b["ref"])))
