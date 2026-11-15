"""Generate synthetic supplier invoices with planted errors and answer keys.

    python -m generator.generate --set tune --count 60
    python -m generator.generate --set holdout --count 40

Reads Lakan's real POs and receipts from the Odoo sandbox, so every invoice refers to
actual orders. The tuning and held-out sets use separate halves of the POs.

Output: data/invoices/<set>/<id>.pdf|.jpg, <id>.json (answer key), manifest.json.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from pathlib import Path

from agent.config import ROOT
from agent.odoo import Odoo

from . import noise
from .render import render_image, render_pdf
from .scenarios import SCENARIO_WEIGHTS, Invoice, InvoiceFactory, expected_status
from .source import load_catalog

RENDER_WEIGHTS = {"pdf": 50, "scan": 30, "photo": 20}
LAYOUT_BY_SUPPLIER = ["classic", "compact", "statement"]
PO_SPLIT_SEED = 7  # fixed, so the tune/holdout PO split never changes
SET_SEEDS = {"tune": 101, "holdout": 202}


def pick(rng: random.Random, weights: dict) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def scenario_plan(rng: random.Random, count: int, pending_available: int) -> list[str]:
    """Fixed quota per scenario (proportional to SCENARIO_WEIGHTS), shuffled.
    Random draws give too few rare error types in a small set; quotas guarantee coverage."""
    total = sum(SCENARIO_WEIGHTS.values())
    quota = {s: max(1, round(w / total * count)) for s, w in SCENARIO_WEIGHTS.items()}
    quota["not_received"] = min(quota["not_received"], pending_available)
    while sum(quota.values()) > count:
        quota["clean"] -= 1
    quota["clean"] += count - sum(quota.values())
    plan = [s for s, n in quota.items() for _ in range(n)]
    rng.shuffle(plan)
    # duplicates need an earlier invoice to copy: keep them out of the first few slots
    for i in range(min(4, len(plan))):
        if plan[i] == "duplicate_invoice":
            j = next(k for k in range(len(plan) - 1, 3, -1) if plan[k] != "duplicate_invoice")
            plan[i], plan[j] = plan[j], plan[i]
    return plan


def answer_key(inv: Invoice, order: int, file: str, render: str, layout: str) -> dict:
    prints_codes = layout != "compact"
    return {
        "invoice_id": inv.invoice_id,
        "order": order,
        "file": file,
        "render": render,
        "layout": layout,
        "scenario": inv.scenario,
        "true_po": inv.true_po,
        "expected_status": expected_status(inv),
        "issues": inv.issues,
        "printed": {
            "supplier_name": inv.supplier_name,
            "supplier_tin": inv.supplier_tin,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "po_number": inv.po_ref_printed,
            "lines": [
                {
                    "supplier_code": l.code if prints_codes else None,
                    "description": l.description,
                    "quantity": l.qty,
                    "unit": l.unit,
                    "unit_price": l.unit_price,
                    "line_total": l.line_total,
                }
                for l in inv.lines
            ],
            "subtotal": inv.subtotal,
            "vat": inv.vat,
            "total": inv.total,
        },
        "line_skus": [l.sku for l in inv.lines],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["tune", "holdout"], required=True)
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--out", default=str(ROOT / "data" / "invoices"))
    args = ap.parse_args()

    catalog = load_catalog(Odoo.from_env())
    pos = sorted(catalog.pos, key=lambda p: p.id)
    split_rng = random.Random(PO_SPLIT_SEED)

    def split(group: list) -> list:
        """60% of each group to tune, 40% to holdout; the two sets never share a PO."""
        group = group[:]
        split_rng.shuffle(group)
        cut = round(len(group) * 0.6)
        return group[:cut] if args.set == "tune" else group[cut:]

    received = split([p for p in pos if p.receipt_status in ("full", "partial")])
    pending = split([p for p in pos if p.receipt_status == "pending"])

    rng = random.Random(SET_SEEDS[args.set])
    rng.shuffle(received)
    rng.shuffle(pending)
    factory = InvoiceFactory(catalog, rng, args.set)

    out_dir = Path(args.out) / args.set
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    layout_of = {p.supplier.id: LAYOUT_BY_SUPPLIER[i % 3] for i, p in enumerate(sorted({p.supplier.id: p for p in pos}.values(), key=lambda p: p.supplier.id))}
    manifest, renders = [], {}

    plan = scenario_plan(rng, args.count, len(pending))
    for order, scenario in enumerate(plan, 1):
        if scenario == "duplicate_invoice":
            earlier = [i for i in factory.issued[:-2] if i.scenario != "duplicate_invoice"]
            if not earlier:
                scenario = "clean"
        if scenario == "not_received" and not pending:
            scenario = "clean"
        if scenario not in ("duplicate_invoice", "not_received") and not received:
            raise SystemExit(f"ran out of received POs for set {args.set}; lower --count or seed more POs")

        if scenario == "duplicate_invoice":
            original = rng.choice(earlier)
            inv = factory.duplicate_of(original)
            supplier_id = next(p.supplier.id for p in pos if p.name == original.true_po)
            # a re-sent invoice usually arrives in a different form
            render = rng.choice([r for r in RENDER_WEIGHTS if r != renders[original.invoice_id]])
        else:
            po = pending.pop() if scenario == "not_received" else received.pop()
            inv = factory.build(po, scenario)
            supplier_id = po.supplier.id
            render = pick(rng, RENDER_WEIGHTS)
        renders[inv.invoice_id] = render
        layout = layout_of[supplier_id]

        if render == "pdf":
            file = f"{inv.invoice_id}.pdf"
            render_pdf(inv, layout, out_dir / file)
        else:
            file = f"{inv.invoice_id}.jpg"
            img = render_image(inv, layout)
            img = noise.scan(img, rng) if render == "scan" else noise.photo(img, rng)
            img.save(out_dir / file, quality=72 if render == "scan" else 82)

        key = answer_key(inv, order, file, render, layout)
        (out_dir / f"{inv.invoice_id}.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
        manifest.append({k: key[k] for k in ("order", "invoice_id", "file", "render", "layout", "scenario", "true_po", "expected_status")})

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    scen = Counter(m["scenario"].split(":")[0] for m in manifest)
    print(f"{args.set}: {len(manifest)} invoices -> {out_dir}")
    print("  scenarios:", dict(scen))
    print("  renders:  ", dict(Counter(m["render"] for m in manifest)))
    print("  status:   ", dict(Counter(m["expected_status"] for m in manifest)))
    print(f"  POs left unused in pool: received={len(received)} pending={len(pending)}")


if __name__ == "__main__":
    main()
