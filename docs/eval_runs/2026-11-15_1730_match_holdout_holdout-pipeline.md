# Matching run: holdout-pipeline (holdout set, extraction source: holdout-final)

| Metric | Result |
|---|---|
| Planted errors caught (recall) | **32/32 (100%)** |
| Flags that were real (precision) | **32/33 (97%)** |
| Clean invoices passed (no false alarm) | 11/12 (92%) |
| Problem invoices sent to review | 28/28 (100%) |
| Correct PO identified | 39/40 (98%) |
| Correct final status | 39/40 (98%) |
| Date warnings raised | 0 |

| Error type | Caught |
|---|---|
| duplicate_invoice | 2/2 |
| math_error | 3/3 |
| missing_po_ref | 4/4 |
| not_received | 3/3 |
| over_billed_qty | 7/7 |
| price_mismatch | 7/7 |
| unknown_item | 4/4 |
| wrong_po_ref | 2/2 |

False alarms by type: extraction_failed (holdout-023)

## Differences

- **holdout-023** (clean, pdf): expected ready, got needs_review; PO None (true P00060); missed: -; extra: extraction_failed
