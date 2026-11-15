# Matching run: pipeline-v1 (tune set, extraction source: flash-lite-v2)

| Metric | Result |
|---|---|
| Planted errors caught (recall) | **48/50 (96%)** |
| Flags that were real (precision) | **48/50 (96%)** |
| Clean invoices passed (no false alarm) | 17/18 (94%) |
| Problem invoices sent to review | 42/42 (100%) |
| Correct PO identified | 58/60 (97%) |
| Correct final status | 59/60 (98%) |
| Date warnings raised | 1 |

| Error type | Caught |
|---|---|
| duplicate_invoice | 2/3 |
| math_error | 5/5 |
| missing_po_ref | 5/5 |
| not_received | 4/5 |
| over_billed_qty | 9/9 |
| price_mismatch | 13/13 |
| unknown_item | 7/7 |
| wrong_po_ref | 3/3 |

False alarms by type: extraction_failed (tune-008, tune-034)

## Differences

- **tune-008** (not_received, photo): expected needs_review, got needs_review; PO None (true P00022); missed: not_received; extra: extraction_failed
- **tune-026** (duplicate_invoice, scan): expected needs_review, got needs_review; PO P00022 (true P00022); missed: duplicate_invoice; extra: -
- **tune-034** (clean, scan): expected ready, got needs_review; PO None (true P00113); missed: -; extra: extraction_failed
