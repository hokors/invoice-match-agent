# Matching run: holdout-key (holdout set, extraction source: key)

| Metric | Result |
|---|---|
| Planted errors caught (recall) | **32/32 (100%)** |
| Flags that were real (precision) | **32/32 (100%)** |
| Clean invoices passed (no false alarm) | 12/12 (100%) |
| Problem invoices sent to review | 28/28 (100%) |
| Correct PO identified | 40/40 (100%) |
| Correct final status | 40/40 (100%) |
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

False alarms by type: none

## Differences

