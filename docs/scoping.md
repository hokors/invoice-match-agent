# Scoping document

Written the way I'd scope this for a real client. The client here is fictional.

## Client

**Lakan Distribution Inc.** (fictional), a Philippine distributor of groceries and household goods.
About 40 active suppliers and 300–500 supplier invoices a month. Uses Odoo for purchasing, inventory and invoicing.

## Problem

- Two AP clerks type every supplier invoice into Odoo by hand, then check it against the PO and the receipt.
- Invoices arrive as PDFs by email, scanned paper, and phone photos sent over Viber.
- Errors that slip through: paying for undelivered goods, paying old prices after a PO was renegotiated, and
  occasionally paying the same invoice twice.

## Goal

Cut the time per invoice and catch more billing errors, **without** letting software pay anyone by itself.

## In scope

- Reading supplier invoices (PDF, scan, photo) into structured data
- Finding the matching PO and goods receipts in Odoo
- Line-level 3-way match: quantity, unit price, totals, VAT
- Duplicate invoice detection
- Creating a **draft** vendor bill in Odoo with a match report attached
- An evaluation suite with a held-out set

## Out of scope

- Posting, approving or paying bills (a person always does this)
- Supplier onboarding, new suppliers without a PO
- Withholding tax and other BIR filing rules beyond a 12% VAT check
- Email or Viber inbox integration (invoices are dropped into a folder for now)

## Success criteria

| Metric | Target |
|---|---|
| Planted-error recall (held-out) | ≥ 90% |
| False alarms on clean invoices | ≤ 10% |
| PO match accuracy | ≥ 95% |
| Processing time per invoice | < 30 s |
| Money-related decisions made by the LLM alone | 0 (all checked by rules) |

## Design principles

1. **Rules for money, AI for reading.** The LLM extracts fields and suggests product-name matches. Every
   quantity, price and total comparison is done in code.
2. **Draft, never post.** The agent only creates draft bills. Anything uncertain is marked *needs review*.
3. **Explain every flag.** Each issue says what was expected, what was found, and where.

## Assumptions

- Self-hosted Odoo 19 Community exposes the external JSON-2 API (verified 2026-11-15).
- Every invoice should have a PO. Invoices without one are flagged, not processed.
- Supplier invoice numbers are unique per supplier.

## Risks

| Risk | Mitigation |
|---|---|
| Poor scans or photos misread | Confidence per field; low confidence → needs review |
| Same product named differently by supplier and PO | Fuzzy matching with a supplier product-code table, LLM as fallback |
| Partial deliveries across several receipts | Match against the sum of receipts per PO line |
| Synthetic invoices too clean to be realistic | Done: 3 layouts, office-scan and phone-photo versions. Not done: handwriting, stamps, multi-page invoices |
