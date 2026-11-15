# Extraction run: holdout-final (holdout set)

40 invoices. Models used: gemini-3.5-flash-lite (39), - (1). Failed calls: 1.
Median latency 2.69s. Tokens: 53,746 in / 16,737 out.

| | Invoices fully correct | All numbers correct |
|---|---|---|
| **All** | **39/40 (98%)** | **39/40 (98%)** |
| pdf | 18/19 (95%) | 18/19 (95%) |
| photo | 10/10 (100%) | 10/10 (100%) |
| scan | 11/11 (100%) | 11/11 (100%) |

| Field | Correct | Accuracy |
|---|---|---|
| supplier_name | 39/40 | 98% |
| supplier_tin | 39/40 | 98% |
| invoice_number | 39/40 | 98% |
| invoice_date | 39/40 | 98% |
| po_number | 39/40 | 98% |
| line_count | 39/40 | 98% |
| line.supplier_code | 122/125 | 98% |
| line.description | 122/125 | 98% |
| line.quantity | 122/125 | 98% |
| line.unit | 122/125 | 98% |
| line.unit_price | 122/125 | 98% |
| line.line_total | 122/125 | 98% |
| subtotal | 39/40 | 98% |
| vat | 39/40 | 98% |
| total | 39/40 | 98% |

## Misses

- **holdout-023** (pdf, classic): all models failed after 4 attempts; last error: gemini-flash-latest: TimeoutError The read operation timed out
