# Extraction run: flash-lite-v1 (tune set)

60 invoices. Models used: gemini-3.5-flash-lite (59), - (1). Failed calls: 1.
Median latency 2.56s. Tokens: 77,364 in / 24,711 out.

| | Invoices fully correct | All numbers correct |
|---|---|---|
| **All** | **50/60 (83%)** | **59/60 (98%)** |
| pdf | 23/27 (85%) | 27/27 (100%) |
| photo | 9/10 (90%) | 10/10 (100%) |
| scan | 18/23 (78%) | 22/23 (96%) |

| Field | Correct | Accuracy |
|---|---|---|
| supplier_name | 59/60 | 98% |
| supplier_tin | 59/60 | 98% |
| invoice_number | 59/60 | 98% |
| invoice_date | 50/60 | 83% |
| po_number | 60/60 | 100% |
| line_count | 59/60 | 98% |
| line.supplier_code | 173/173 | 100% |
| line.description | 171/173 | 99% |
| line.quantity | 171/173 | 99% |
| line.unit | 171/173 | 99% |
| line.unit_price | 171/173 | 99% |
| line.line_total | 171/173 | 99% |
| subtotal | 59/60 | 98% |
| vat | 59/60 | 98% |
| total | 59/60 | 98% |

## Misses

- **tune-010** (scan, classic): invoice_date: expected '2026-11-06', got '2026-06-11'
- **tune-023** (scan, classic): invoice_date: expected '2026-11-05', got '2026-05-11'
- **tune-025** (scan, classic): invoice_date: expected '2026-09-05', got '2026-05-09'
- **tune-033** (pdf, classic): invoice_date: expected '2026-10-03', got '2026-03-10'
- **tune-040** (scan, compact): all models failed after 4 attempts; last error: gemini-flash-latest: TimeoutError The read operation timed out
- **tune-043** (pdf, classic): invoice_date: expected '2026-10-03', got '2026-03-10'
- **tune-048** (pdf, classic): invoice_date: expected '2026-10-09', got '2026-09-10'
- **tune-052** (pdf, classic): invoice_date: expected '2026-11-04', got '2026-04-11'
- **tune-055** (scan, classic): invoice_date: expected '2026-10-11', got '2026-11-10'
- **tune-057** (photo, classic): invoice_date: expected '2026-11-04', got '2026-04-11'
