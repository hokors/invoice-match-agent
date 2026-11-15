# Extraction run: flash-lite-v2 (tune set)

60 invoices. Models used: gemini-3.5-flash-lite (58), - (2). Failed calls: 2.
Median latency 2.3s. Tokens: 79,856 in / 24,261 out.

| | Invoices fully correct | All numbers correct |
|---|---|---|
| **All** | **57/60 (95%)** | **58/60 (97%)** |
| pdf | 27/27 (100%) | 27/27 (100%) |
| photo | 9/10 (90%) | 9/10 (90%) |
| scan | 21/23 (91%) | 22/23 (96%) |

| Field | Correct | Accuracy |
|---|---|---|
| supplier_name | 58/60 | 97% |
| supplier_tin | 58/60 | 97% |
| invoice_number | 58/60 | 97% |
| invoice_date | 57/60 | 95% |
| po_number | 58/60 | 97% |
| line_count | 58/60 | 97% |
| line.supplier_code | 171/173 | 99% |
| line.description | 168/173 | 97% |
| line.quantity | 168/173 | 97% |
| line.unit | 168/173 | 97% |
| line.unit_price | 168/173 | 97% |
| line.line_total | 168/173 | 97% |
| subtotal | 58/60 | 97% |
| vat | 58/60 | 97% |
| total | 58/60 | 97% |

## Misses

- **tune-008** (photo, statement): all models failed after 4 attempts; last error: gemini-flash-latest: TimeoutError The read operation timed out
- **tune-025** (scan, classic): invoice_date: expected '2026-09-05', got '2026-05-09'
- **tune-034** (scan, compact): all models failed after 4 attempts; last error: gemini-flash-latest: TimeoutError The read operation timed out
