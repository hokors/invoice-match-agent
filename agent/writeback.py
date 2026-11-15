"""Creates DRAFT vendor bills in Odoo from a match report. Never posts or pays anything.

Each bill gets:
  - the supplier, invoice number (Reference), date and PO (Origin)
  - one line per invoice line, linked to its PO line when matched, so Odoo tracks billed quantities
  - the original invoice file attached
  - the match report in the notes and the chatter
  - a To-Do activity "Review invoice issues" when the status is needs_review

Bills made by the agent carry a marker in their notes so `remove_agent_drafts` can clean them up.
"""
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path

from .context import OdooContext, norm_code
from .odoo import Odoo

MARKER = "Created by invoice-match-agent"


def _report_html(report: dict, file_name: str) -> str:
    status = "Ready for approval" if report["status"] == "ready" else "Needs review"
    color = "#1e7e34" if report["status"] == "ready" else "#b8860b"
    parts = [
        f'<p><b style="color:{color}">{status}</b> — 3-way match against {html.escape(report.get("po") or "no PO")}'
        f" (source file: {html.escape(file_name)})</p>"
    ]
    if report["issues"]:
        parts.append("<ul>" + "".join(f"<li>{html.escape(i['message'])}</li>" for i in report["issues"]) + "</ul>")
    else:
        parts.append("<p>Quantities match goods received, prices match the PO, totals and 12% VAT add up, no duplicate found.</p>")
    parts.append(f"<p><i>{MARKER}. Draft only: a person must review and confirm.</i></p>")
    return "".join(parts)


class BillWriter:
    def __init__(self, odoo: Odoo, ctx: OdooContext):
        self.odoo = odoo
        self.ctx = ctx
        self._todo_type = None

    def _line_vals(self, inv_line: dict, rep_line: dict) -> dict:
        vals = {
            "name": inv_line.get("description") or "Invoice line",
            "quantity": inv_line.get("quantity") or 0,
            "price_unit": inv_line.get("unit_price") or 0,
        }
        if self.ctx.purchase_tax_id:
            vals["tax_ids"] = [[6, 0, [self.ctx.purchase_tax_id]]]
        if rep_line and rep_line.get("product_id"):
            vals["product_id"] = rep_line["product_id"]
        if rep_line and rep_line.get("po_line_id"):
            vals["purchase_line_id"] = rep_line["po_line_id"]
        return vals

    def write(self, inv: dict, report: dict, file: Path) -> int:
        """Create the draft bill and return its id."""
        rep_lines = report.get("lines") or []
        vals = {
            "move_type": "in_invoice",
            "narration": _report_html(report, file.name),
            "invoice_line_ids": [[0, 0, self._line_vals(l, rep_lines[i] if i < len(rep_lines) else {})]
                                 for i, l in enumerate(inv.get("lines") or [])],
        }
        if report.get("supplier_id"):
            vals["partner_id"] = report["supplier_id"]
        if inv.get("invoice_number"):
            vals["ref"] = inv["invoice_number"]
        if inv.get("invoice_date"):
            vals["invoice_date"] = inv["invoice_date"]
        if report.get("po"):
            vals["invoice_origin"] = report["po"]

        bill_id = self.odoo.call("account.move", "create", vals_list=[vals])[0]

        attachment_id = self.odoo.call("ir.attachment", "create", vals_list=[{
            "name": file.name,
            "datas": base64.b64encode(file.read_bytes()).decode(),
            "res_model": "account.move",
            "res_id": bill_id,
            "mimetype": mimetypes.guess_type(file.name)[0] or "application/octet-stream",
        }])[0]
        self.odoo.call("account.move", "message_post", ids=[bill_id], body=_report_html(report, file.name),
                       attachment_ids=[attachment_id], message_type="comment", subtype_xmlid="mail.mt_note")
        if report["status"] != "ready":
            summary = "Enter invoice manually" if any(i["type"] == "extraction_failed" for i in report["issues"]) else "Review invoice issues"
            self.odoo.call("account.move", "activity_schedule", ids=[bill_id], act_type_xmlid="mail.mail_activity_data_todo",
                           summary=summary, note="; ".join(i["message"] for i in report["issues"])[:2000])

        # Keep the in-memory context current, so later invoices in the same run see this bill.
        if report.get("supplier_id") and inv.get("invoice_number"):
            self.ctx.billed_refs.add((report["supplier_id"], norm_code(inv["invoice_number"])))
        po = self.ctx.pos_by_name.get(norm_code(report.get("po"))) if report.get("po") else None
        if po:
            for inv_line, rep_line in zip(inv.get("lines") or [], rep_lines):
                pid = rep_line.get("product_id")
                if rep_line.get("po_line_id") and pid in po.lines:
                    po.lines[pid].qty_invoiced += inv_line.get("quantity") or 0
        return bill_id


def remove_agent_drafts(odoo: Odoo) -> int:
    """Delete draft vendor bills created by the agent (resets the sandbox for evaluation runs)."""
    ids = [b["id"] for b in odoo.search_read(
        "account.move", [["move_type", "=", "in_invoice"], ["state", "=", "draft"], ["narration", "ilike", MARKER]], ["id"])]
    if ids:
        odoo.call("account.move", "unlink", ids=ids)
    return len(ids)
