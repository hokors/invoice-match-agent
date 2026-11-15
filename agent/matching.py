"""3-way match: extracted invoice vs. purchase order vs. goods received.

All money and quantity checks are plain code. The only fuzzy step is matching an invoice line's
printed description to a product when no supplier code is printed.

    ctx = OdooContext(Odoo.from_env())
    report = Matcher(ctx).match(extracted_invoice)
    report["status"]   # "ready" or "needs_review"
    report["issues"]   # each with a type, the numbers involved, and a plain-language message
"""
from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher

from .context import OdooContext, PurchaseOrder, Supplier, SupplierProduct, digits, norm_code

VAT_RATE = 0.12
MONEY_TOL = 0.01
NAME_MATCH_MIN = 0.75


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def peso(x) -> str:
    return f"₱{x:,.2f}" if isinstance(x, (int, float)) else str(x)


def num(x) -> str:
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


class Matcher:
    def __init__(self, ctx: OdooContext, today: date | None = None):
        self.ctx = ctx
        self.today = today or date.today()
        self.ledger: set[tuple[int, str]] = set()  # invoices seen in this run (for duplicates not yet in Odoo)

    # --- identification ---------------------------------------------------------
    def find_supplier(self, inv: dict) -> Supplier | None:
        tin = digits(inv.get("supplier_tin"))
        if len(tin) >= 9:
            for s in self.ctx.suppliers.values():
                if s.tin[:9] == tin[:9]:
                    return s
        best = max(self.ctx.suppliers.values(), key=lambda s: _ratio(s.name, inv.get("supplier_name") or ""), default=None)
        if best and _ratio(best.name, inv.get("supplier_name") or "") >= 0.8:
            return best
        return None

    def find_product(self, sup: Supplier, line: dict) -> SupplierProduct | None:
        code = norm_code(line.get("supplier_code"))
        if code:
            for p in sup.products:
                if code in (norm_code(p.supplier_code), norm_code(p.sku)):
                    return p
        desc = line.get("description") or ""
        scored = [(max(_ratio(desc, p.supplier_name), _ratio(desc, p.name)), p) for p in sup.products]
        score, best = max(scored, key=lambda t: t[0], default=(0, None))
        return best if score >= NAME_MATCH_MIN else None

    @staticmethod
    def _fit(po: PurchaseOrder, matched: list[tuple[dict, SupplierProduct | None]]) -> tuple[float, float]:
        """(share of invoice products on this PO, total quantity gap vs. received). Higher, then lower, is better."""
        prods = [p for _, p in matched if p]
        if not prods:
            return 0.0, float("inf")
        on_po = [p for p in prods if p.product_id in po.lines]
        gap = sum(abs((l.get("quantity") or 0) - po.lines[p.product_id].qty_received)
                  for l, p in matched if p and p.product_id in po.lines)
        return len(on_po) / len(prods), gap

    def choose_po(self, sup: Supplier, inv: dict, matched) -> tuple[PurchaseOrder | None, list[dict]]:
        issues = []
        ranked = sorted(sup.pos, key=lambda po: (-self._fit(po, matched)[0], self._fit(po, matched)[1], po.name))
        best = ranked[0] if ranked and self._fit(ranked[0], matched)[0] > 0 else None
        printed_raw = inv.get("po_number")
        printed = self.ctx.pos_by_name.get(norm_code(printed_raw)) if printed_raw else None

        if not printed_raw:
            issues.append({"type": "missing_po_ref",
                           "message": f"No PO reference on the invoice. Best match by items and quantities: {best.name if best else 'none found'}."})
            return best, issues
        if printed is None or printed.supplier_id != sup.id:
            why = "doesn't exist" if printed is None else "belongs to another supplier"
            issues.append({"type": "wrong_po_ref", "printed": printed_raw, "actual": best.name if best else None,
                           "message": f"Invoice cites PO {printed_raw}, which {why}. Items match {best.name if best else 'no open PO'}."})
            return best, issues
        p_share, p_gap = self._fit(printed, matched)
        if best and best is not printed:
            b_share, b_gap = self._fit(best, matched)
            # Trust the printed PO. Override it only when another PO fits exactly (every item, every quantity)
            # and the printed one doesn't, and the gap isn't simply over-billing on the printed PO.
            # (An extra item on the invoice lowers the printed PO's fit too; that's an unknown item, not a wrong PO.)
            exact_other = b_share == 1 and b_gap == 0
            printed_exact = p_share == 1 and p_gap == 0
            if p_share == 0 or (exact_other and not printed_exact and not self._explained_by_billing(printed, matched)
                                and not self._explained_by_extra_items(printed, matched)):
                issues.append({"type": "wrong_po_ref", "printed": printed_raw, "actual": best.name,
                               "message": f"Invoice cites PO {printed_raw}, but its items and quantities match {best.name}."})
                return best, issues
        return printed, issues

    @staticmethod
    def _explained_by_billing(po: PurchaseOrder, matched) -> bool:
        """A quantity gap on the cited PO is just over-billing (billed = ordered), not a wrong reference."""
        for l, p in matched:
            if p and p.product_id in po.lines:
                pl = po.lines[p.product_id]
                if abs((l.get("quantity") or 0) - pl.qty_received) > 1e-6 and abs((l.get("quantity") or 0) - pl.qty_ordered) > 1e-6:
                    return False
        return True

    @staticmethod
    def _explained_by_extra_items(po: PurchaseOrder, matched) -> bool:
        """Every line that IS on the cited PO matches its received quantity; the misfit is only extra items."""
        on_po = [(l, p) for l, p in matched if p and p.product_id in po.lines]
        return bool(on_po) and len(on_po) < len(matched) and all(
            abs((l.get("quantity") or 0) - po.lines[p.product_id].qty_received) < 1e-6 for l, p in on_po)

    # --- checks -------------------------------------------------------------------
    def check_lines(self, po: PurchaseOrder, matched) -> list[dict]:
        issues = []
        received_any = po.received_anything
        if not received_any:
            issues.append({"type": "not_received", "po": po.name,
                           "message": f"Nothing on {po.name} has been received yet; don't pay before the goods arrive."})
        for line, prod in matched:
            label = line.get("description") or line.get("supplier_code") or "?"
            if prod is None or prod.product_id not in po.lines:
                issues.append({"type": "unknown_item", "description": label, "sku": prod.sku if prod else None,
                               "message": f"'{label}' is billed but isn't on {po.name}."})
                continue
            pl = po.lines[prod.product_id]
            qty, price = line.get("quantity") or 0, line.get("unit_price")
            available = pl.qty_received - pl.qty_invoiced
            if received_any and qty > available + 1e-6:
                issues.append({"type": "over_billed_qty", "sku": prod.sku, "billed_qty": qty, "received_qty": pl.qty_received,
                               "message": f"{prod.name}: billed {num(qty)}, only {num(pl.qty_received)} received"
                                          + (f" ({num(pl.qty_invoiced)} already billed)" if pl.qty_invoiced else "") + "."})
            if price is not None and abs(price - pl.price) > MONEY_TOL:
                issues.append({"type": "price_mismatch", "sku": prod.sku, "billed_price": price, "po_price": pl.price,
                               "message": f"{prod.name}: billed {peso(price)}/unit, PO price is {peso(pl.price)}."})
        return issues

    @staticmethod
    def check_math(inv: dict, matched) -> list[dict]:
        issues = []
        for line, prod in matched:
            q, p, t = line.get("quantity"), line.get("unit_price"), line.get("line_total")
            if None not in (q, p, t) and abs(q * p - t) > MONEY_TOL:
                issues.append({"type": "math_error", "where": "line_total", "sku": prod.sku if prod else None,
                               "printed": t, "correct": round(q * p, 2),
                               "message": f"Line '{line.get('description')}': {num(q)} × {peso(p)} = {peso(q * p)}, invoice says {peso(t)}."})
        lines_sum = round(sum(l.get("line_total") or 0 for l, _ in matched), 2)
        sub, vat, total = inv.get("subtotal"), inv.get("vat"), inv.get("total")
        if sub is not None and abs(sub - lines_sum) > MONEY_TOL:
            issues.append({"type": "math_error", "where": "subtotal", "printed": sub, "correct": lines_sum,
                           "message": f"Lines add up to {peso(lines_sum)}, invoice subtotal says {peso(sub)}."})
        if sub is not None and vat is not None and abs(round(sub * VAT_RATE, 2) - vat) > 0.02:
            issues.append({"type": "math_error", "where": "vat", "printed": vat, "correct": round(sub * VAT_RATE, 2),
                           "message": f"12% VAT on {peso(sub)} is {peso(sub * VAT_RATE)}, invoice says {peso(vat)}."})
        if None not in (sub, vat, total) and abs(sub + vat - total) > 0.02:
            issues.append({"type": "math_error", "where": "total", "printed": total, "correct": round(sub + vat, 2),
                           "message": f"Subtotal + VAT = {peso(sub + vat)}, invoice total says {peso(total)}."})
        return issues

    def check_duplicate(self, sup: Supplier, inv: dict) -> list[dict]:
        key = (sup.id, norm_code(inv.get("invoice_number")))
        if not key[1]:
            return []
        seen = key in self.ctx.billed_refs or key in self.ledger
        self.ledger.add(key)
        if seen:
            return [{"type": "duplicate_invoice", "invoice_number": inv.get("invoice_number"),
                     "message": f"{sup.name} invoice {inv.get('invoice_number')} was already received. Possible double payment."}]
        return []

    def check_date(self, po: PurchaseOrder, inv: dict) -> list[dict]:
        raw = inv.get("invoice_date")
        try:
            d = date.fromisoformat(raw)
        except (TypeError, ValueError):
            return [{"type": "date_check", "message": f"Invoice date '{raw}' couldn't be read."}]
        if d < date.fromisoformat(po.date_order) or d > self.today:
            return [{"type": "date_check", "invoice_date": raw, "po_date": po.date_order,
                     "message": f"Invoice date {raw} is {'before the PO date ' + po.date_order if d < date.fromisoformat(po.date_order) else 'in the future'}; check it was read correctly."}]
        return []

    # --- main ---------------------------------------------------------------------
    def match(self, inv: dict) -> dict:
        if not inv or not inv.get("lines"):
            return {"status": "needs_review", "supplier": None, "po": None,
                    "issues": [{"type": "extraction_failed", "message": "The invoice couldn't be read. A person needs to enter it."}]}
        sup = self.find_supplier(inv)
        if sup is None:
            return {"status": "needs_review", "supplier": None, "po": None,
                    "issues": [{"type": "unknown_supplier", "message": f"Supplier '{inv.get('supplier_name')}' isn't in Odoo."}]}

        matched = [(line, self.find_product(sup, line)) for line in inv["lines"]]
        issues = self.check_duplicate(sup, inv)
        po, po_issues = self.choose_po(sup, inv, matched)
        issues += po_issues
        if po is None:
            issues.append({"type": "no_po_found", "message": f"No open PO from {sup.name} matches these items."})
            return {"status": "needs_review", "supplier": sup.name, "supplier_id": sup.id, "po": None, "issues": issues}

        issues += self.check_lines(po, matched)
        issues += self.check_math(inv, matched)
        issues += self.check_date(po, inv)
        lines = [{"description": l.get("description"), "sku": p.sku if p else None,
                  "product_id": p.product_id if p else None,
                  "po_line_id": po.lines[p.product_id].id if p and p.product_id in po.lines else None,
                  "billed_qty": l.get("quantity"), "billed_price": l.get("unit_price"),
                  "po_qty": po.lines[p.product_id].qty_ordered if p and p.product_id in po.lines else None,
                  "received_qty": po.lines[p.product_id].qty_received if p and p.product_id in po.lines else None,
                  "po_price": po.lines[p.product_id].price if p and p.product_id in po.lines else None}
                 for l, p in matched]
        return {"status": "needs_review" if issues else "ready", "supplier": sup.name, "supplier_id": sup.id,
                "po": po.name, "po_id": po.id, "issues": issues, "lines": lines}
