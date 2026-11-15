# Failure log

What went wrong, why, and what changed. Newest at the bottom.

| # | Date | Stage | What happened | Cause | Fix / status |
|---|---|---|---|---|---|
| 1 | 2026-11-15 | Setup | `docker` engine unreachable right after install | WSL wasn't installed; Windows needed a restart after enabling Virtual Machine Platform | Enabled the feature, installed WSL, restarted. Docker data on D:. |
| 2 | 2026-11-15 | Seed | Seeding failed: `Invalid field 'taxes_id' on model 'purchase.order.line'` | Odoo 19 renamed the field to `tax_ids` | Renamed in `seed_lakan.py`; reset script now prints errors instead of exiting silently. |
| 3 | 2026-11-15 | Generator | Only 1 unknown-item and 2 math-error invoices in a 60-invoice set | Scenarios were drawn at random; rare types get starved in small sets | Fixed quota per error type, then shuffled. |
| 4 | 2026-11-15 | Generator | Classic layout printed "No. No. 001234" | One invoice-number style already contained "No." and the layout adds it again | Number style is digits only; the layout adds the label. |
| 5 | 2026-11-15 | Extraction | 9 of 60 invoices had **day and month swapped** (10/03/2026 read as March 10) | The classic layout uses MM/DD/YYYY (common in the Philippines); the model assumed DD/MM | Prompt rule: slash dates on PH invoices are month/day/year. Invoices fully correct 83% → 95%. One scan still flips; the matching step will flag invoice dates that don't fit the PO/receipt dates. |
| 6 | 2026-11-15 | Extraction | 1–2 invoices per run fail with timeouts on **both** models | Gemini Flash overloaded (same as in the triage project); occasional Flash-Lite timeouts too | Flash-Lite is the main model, Flash the fallback. A failed extraction becomes "needs review", never silently dropped. |
| 7 | 2026-11-15 | Matching | Unknown-item invoices caught 0/7; instead the agent accused them of citing the wrong PO and raised fake over-billing flags | An extra item lowers the cited PO's fit, so the matcher switched to another PO that happened to contain the other items | Trust the printed PO; override only when another PO fits exactly (every item and quantity) and the misfit isn't explained by extra items or over-billing. Answer-key run: recall 86% → 100%, precision 74% → 100%. |
| 8 | 2026-11-15 | Pipeline | A duplicate invoice slipped past duplicate detection | Its original had failed extraction (API timeout), so it was never recorded as received | Open: failed extractions should still be logged as "received, pending manual entry" so later copies are caught. |

