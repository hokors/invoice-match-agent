"""Evaluate the 3-way matcher against the answer keys.

    python -m evals.matching --set tune --source key            # perfect extraction: tests matching logic only
    python -m evals.matching --set tune --source flash-lite-v2  # real Gemini extractions: tests the whole pipeline

Invoices are processed in their manifest order, so duplicates are detected the way they'd arrive.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime

from agent.config import ROOT
from agent.context import OdooContext
from agent.matching import Matcher
from agent.odoo import Odoo

WARNING_TYPES = {"date_check"}  # extra checks with no planted counterpart; reported separately


def issue_key(i: dict):
    t = i["type"]
    if t in ("over_billed_qty", "price_mismatch"):
        return t, i.get("sku")
    if t == "math_error":
        return t, i.get("where")
    return t, None


def pct(a, b):
    return f"{a / b:.0%}" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["tune", "holdout"], default="tune")
    ap.add_argument("--source", default="key", help="'key' for answer-key data, or an extraction label in data/extractions/<set>/")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()
    label = args.label or args.source

    set_dir = ROOT / "data" / "invoices" / args.set
    manifest = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))
    matcher = Matcher(OdooContext(Odoo.from_env()))

    planted_by_type, found_by_type = Counter(), Counter()
    tp = fp = warnings = 0
    po_ok = status_ok = 0
    clean_total = clean_passed = bad_total = bad_caught = 0
    rows, fps = [], defaultdict(list)

    for entry in manifest:
        key = json.loads((set_dir / f"{entry['invoice_id']}.json").read_text(encoding="utf-8"))
        if args.source == "key":
            inv = key["printed"]
        else:
            cached = ROOT / "data" / "extractions" / args.set / args.source / f"{entry['invoice_id']}.json"
            inv = json.loads(cached.read_text(encoding="utf-8"))["extraction"] if cached.exists() else {}
        report = matcher.match(inv)

        planted = Counter(issue_key(i) for i in key["issues"])
        detected = [i for i in report["issues"] if i["type"] not in WARNING_TYPES]
        warnings += len(report["issues"]) - len(detected)
        det = Counter(issue_key(i) for i in detected)
        for k, n in planted.items():
            planted_by_type[k[0]] += n
            found_by_type[k[0]] += min(n, det.get(k, 0))
        for k, n in det.items():
            hit = min(n, planted.get(k, 0))
            tp += hit
            if n > hit:
                fp += n - hit
                fps[k[0]].append(entry["invoice_id"])

        po_ok += report["po"] == key["true_po"]
        status_ok += report["status"] == key["expected_status"]
        if key["expected_status"] == "ready":
            clean_total += 1
            clean_passed += report["status"] == "ready"
        else:
            bad_total += 1
            bad_caught += report["status"] == "needs_review"

        missed = [f"{t}{'(' + str(s) + ')' if s else ''}" for (t, s), n in planted.items() if det.get((t, s), 0) < n]
        extra = [f"{t}{'(' + str(s) + ')' if s else ''}" for (t, s), n in det.items() if planted.get((t, s), 0) < n]
        rows.append({"invoice_id": entry["invoice_id"], "render": entry["render"], "scenario": key["scenario"],
                     "expected": key["expected_status"], "got": report["status"], "true_po": key["true_po"],
                     "matched_po": report["po"], "missed": "; ".join(missed), "extra": "; ".join(extra),
                     "messages": " | ".join(i["message"] for i in report["issues"])})
        ok = report["status"] == key["expected_status"] and not missed and not extra
        print(f"[{'OK  ' if ok else 'DIFF'}] {entry['invoice_id']} {key['scenario']:<32} {report['status']:<12} "
              f"{'missed=' + ','.join(missed) if missed else ''} {'extra=' + ','.join(extra) if extra else ''}")

    n = len(rows)
    planted_total = sum(planted_by_type.values())
    found_total = sum(found_by_type.values())
    lines = [
        f"# Matching run: {label} ({args.set} set, extraction source: {args.source})",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Planted errors caught (recall) | **{found_total}/{planted_total} ({pct(found_total, planted_total)})** |",
        f"| Flags that were real (precision) | **{tp}/{tp + fp} ({pct(tp, tp + fp)})** |",
        f"| Clean invoices passed (no false alarm) | {clean_passed}/{clean_total} ({pct(clean_passed, clean_total)}) |",
        f"| Problem invoices sent to review | {bad_caught}/{bad_total} ({pct(bad_caught, bad_total)}) |",
        f"| Correct PO identified | {po_ok}/{n} ({pct(po_ok, n)}) |",
        f"| Correct final status | {status_ok}/{n} ({pct(status_ok, n)}) |",
        f"| Date warnings raised | {warnings} |",
        "",
        "| Error type | Caught |",
        "|---|---|",
        *[f"| {t} | {found_by_type[t]}/{planted_by_type[t]} |" for t in sorted(planted_by_type)],
        "",
        "False alarms by type: " + (", ".join(f"{t} ({', '.join(v)})" for t, v in fps.items()) or "none"),
        "",
        "## Differences",
        "",
        *[f"- **{r['invoice_id']}** ({r['scenario']}, {r['render']}): expected {r['expected']}, got {r['got']}; "
          f"PO {r['matched_po']} (true {r['true_po']}); missed: {r['missed'] or '-'}; extra: {r['extra'] or '-'}"
          for r in rows if r["missed"] or r["extra"] or r["expected"] != r["got"]],
    ]
    print("\n" + "\n".join(lines[: 22 + len(planted_by_type)]))

    out = ROOT / "docs" / "eval_runs"
    out.mkdir(parents=True, exist_ok=True)
    base = out / f"{datetime.now():%Y-%m-%d_%H%M}_match_{args.set}_{label}"
    base.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved {base.relative_to(ROOT)}.md/.csv")


if __name__ == "__main__":
    main()
