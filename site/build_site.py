"""Builds the results website's data from the evaluation reports and answer keys.

    python site/build_site.py

Writes site/public/data.json and site/public/invoices/<id>.jpg (small previews of every test invoice).
Every number on the site comes from docs/eval_runs/ and data/invoices/ - nothing is typed in by hand.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "docs" / "eval_runs"
OUT = ROOT / "site" / "public"
PREVIEW_W = 760


def latest(pattern: str) -> Path:
    files = sorted(RUNS.glob(pattern))
    if not files:
        sys.exit(f"missing eval report: {pattern}")
    return files[-1]


def frac(text: str) -> list[int]:
    m = re.search(r"(\d+)/(\d+)", text)
    return [int(m.group(1)), int(m.group(2))] if m else [0, 0]


def md_rows(path: Path) -> dict[str, str]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and not set(cells[0]) <= {"-"}:
            rows[cells[0]] = cells[1:]
    return rows


def extraction_run(pattern: str, label: str, set_name: str) -> dict:
    rows = md_rows(latest(pattern))
    return {"label": label, "set": set_name,
            **{k: frac(rows[k][0]) for k in ("All", "pdf", "scan", "photo") if k in rows}}


MATCH_METRICS = {
    "recall": "Planted errors caught (recall)",
    "precision": "Flags that were real (precision)",
    "clean": "Clean invoices passed (no false alarm)",
    "review": "Problem invoices sent to review",
    "po": "Correct PO identified",
    "status": "Correct final status",
}
ISSUE_TYPES = ["over_billed_qty", "price_mismatch", "unknown_item", "missing_po_ref", "wrong_po_ref",
               "math_error", "not_received", "duplicate_invoice"]


def matching_run(pattern: str, label: str, set_name: str, data: str) -> dict:
    rows = md_rows(latest(pattern))
    return {"label": label, "set": set_name, "data": data,
            "metrics": {k: frac(rows[v][0]) for k, v in MATCH_METRICS.items()},
            "types": {t: frac(rows[t][0]) for t in ISSUE_TYPES if t in rows}}


def describe(issue: dict) -> str:
    t = issue["type"]
    if t == "over_billed_qty":
        return f"Over-billed {issue.get('sku')}: billed {issue['billed_qty']:g}, received {issue['received_qty']:g}"
    if t == "price_mismatch":
        return f"Price of {issue.get('sku')} raised: ₱{issue['billed_price']:,.2f} vs PO ₱{issue['po_price']:,.2f}"
    if t == "unknown_item":
        return f"Added an item not on the PO: {issue.get('description')}"
    if t == "missing_po_ref":
        return "PO reference left off the invoice"
    if t == "wrong_po_ref":
        return f"Wrong PO cited: {issue['printed']} (really {issue['actual']})"
    if t == "math_error":
        return f"Math error in the {issue['where'].replace('_', ' ')}: printed ₱{issue['printed']:,.2f}, should be ₱{issue['correct']:,.2f}"
    if t == "not_received":
        return f"Billed before anything on {issue['po']} was delivered"
    if t == "duplicate_invoice":
        return f"Duplicate of {issue['of']}"
    return t


def invoices(set_name: str, extract_label: str, match_label: str) -> list[dict]:
    set_dir = ROOT / "data" / "invoices" / set_name
    ext = {r["invoice_id"]: r for r in csv.DictReader(latest(f"*_extract_{set_name}_{extract_label}.csv").open(encoding="utf-8"))}
    mat = {r["invoice_id"]: r for r in csv.DictReader(latest(f"*_match_{set_name}_{match_label}.csv").open(encoding="utf-8"))}
    out = []
    for entry in json.loads((set_dir / "manifest.json").read_text(encoding="utf-8")):
        iid = entry["invoice_id"]
        key = json.loads((set_dir / f"{iid}.json").read_text(encoding="utf-8"))
        e, m = ext[iid], mat[iid]
        out.append({
            "id": iid, "set": set_name, "render": entry["render"], "layout": entry["layout"],
            "scenario": key["scenario"].split(":")[0].replace("combo", "two errors"),
            "supplier": key["printed"]["supplier_name"], "number": key["printed"]["invoice_number"],
            "total": key["printed"]["total"], "true_po": key["true_po"], "matched_po": m["matched_po"] or None,
            "expected": key["expected_status"], "got": m["got"],
            "correct": m["got"] == key["expected_status"] and not m["missed"] and not m["extra"],
            "planted": [describe(i) for i in key["issues"]],
            "agent": [s for s in m["messages"].split(" | ") if s],
            "read_ok": e["all_ok"] == "True", "seconds": float(e["seconds"] or 0),
            "api_error": bool(e["error"]),
            "preview": f"invoices/{iid}.jpg",
        })
    return out


def previews(rows: list[dict]):
    import pymupdf
    from PIL import Image

    (OUT / "invoices").mkdir(parents=True, exist_ok=True)
    for r in rows:
        src = ROOT / "data" / "invoices" / r["set"] / (r["id"] + (".pdf" if r["render"] == "pdf" else ".jpg"))
        dst = OUT / r["preview"]
        if src.suffix == ".pdf":
            page = pymupdf.open(src)[0]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(PREVIEW_W / page.rect.width, PREVIEW_W / page.rect.width))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        else:
            img = Image.open(src).convert("RGB")
            img = img.resize((PREVIEW_W, int(img.height * PREVIEW_W / img.width)), Image.LANCZOS)
        img.save(dst, quality=70, optimize=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = invoices("tune", "flash-lite-v2", "pipeline-v1") + invoices("holdout", "holdout-final", "holdout-pipeline")
    data = {
        "extraction": [
            extraction_run("*_extract_tune_flash-lite-v1.md", "Prompt v1", "tune"),
            extraction_run("*_extract_tune_flash-lite-v2.md", "Prompt v2", "tune"),
            extraction_run("*_extract_holdout_holdout-final.md", "Held-out", "holdout"),
        ],
        "matching": [
            matching_run("*_match_tune_key-v1.md", "First version", "tune", "perfect"),
            matching_run("*_match_tune_key-v2.md", "After the PO fix", "tune", "perfect"),
            matching_run("*_match_tune_pipeline-v1.md", "Tuning, full pipeline", "tune", "real"),
            matching_run("*_match_holdout_holdout-pipeline.md", "Held-out, full pipeline", "holdout", "real"),
        ],
        "invoices": rows,
    }
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    previews(rows)
    size = sum(f.stat().st_size for f in (OUT / "invoices").glob("*.jpg")) / 1e6
    print(f"data.json: {len(rows)} invoices; previews: {size:.1f} MB")


if __name__ == "__main__":
    main()
