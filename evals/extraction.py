"""Run invoice extraction over a generated set and score it field by field.

    python -m evals.extraction --set tune --label flash
    python -m evals.extraction --set tune --models gemini-flash-lite-latest --label flash-lite
    python -m evals.extraction --set tune --self-test      # score the answer keys against themselves (no API)

Extractions are cached in data/extractions/<set>/<label>/ so re-scoring is free; use --rerun to call the API again.
Reports go to docs/eval_runs/<timestamp>_extract_<set>_<label>.md (+ .csv).
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from agent.config import ROOT

from .score import HEADER_FIELDS, LINE_FIELDS, MONEY_FIELDS, score_invoice

FIELD_ORDER = HEADER_FIELDS + ["line_count"] + [f"line.{f}" for f in LINE_FIELDS] + MONEY_FIELDS


def pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["tune", "holdout"], default="tune")
    ap.add_argument("--models", nargs="+", default=None, help="model order, first = main (default: flash, then flash-lite)")
    ap.add_argument("--label", default="run")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between API calls (free-tier limits)")
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--self-test", action="store_true", help="no API: check the scorer gives 100%% on the keys")
    args = ap.parse_args()

    set_dir = ROOT / "data" / "invoices" / args.set
    manifest = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))
    if args.limit:
        manifest = manifest[: args.limit]
    cache = ROOT / "data" / "extractions" / args.set / args.label
    cache.mkdir(parents=True, exist_ok=True)

    extractor = None
    if not args.self_test:
        from agent.extract import Extractor
        from agent.gemini import Gemini
        extractor = Extractor(Gemini.from_env(args.models))

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_render: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # all_ok, numbers_ok, n
    rows, errors, secs, tokens_in, tokens_out, models = [], 0, [], 0, 0, defaultdict(int)

    for i, entry in enumerate(manifest):
        key = json.loads((set_dir / f"{entry['invoice_id']}.json").read_text(encoding="utf-8"))
        cached = cache / f"{entry['invoice_id']}.json"
        if args.self_test:
            got, meta = key["printed"], {"model": "answer-key", "seconds": 0}
        elif cached.exists() and not args.rerun:
            saved = json.loads(cached.read_text(encoding="utf-8"))
            got, meta = saved["extraction"], saved["meta"]
        else:
            if i and args.delay:
                time.sleep(args.delay)
            try:
                got, res = extractor.extract(set_dir / entry["file"])
                meta = {"model": res.model, "seconds": res.seconds, "input_tokens": res.input_tokens,
                        "output_tokens": res.output_tokens, "attempts": res.attempts}
            except Exception as e:  # keep going; count it as a failed extraction
                got, meta = {}, {"model": "-", "seconds": 0, "error": str(e)[:300]}
            cached.write_text(json.dumps({"extraction": got, "meta": meta}, indent=2), encoding="utf-8")

        s = score_invoice(got, key["printed"])
        for f, (ok, n) in s["counts"].items():
            totals[f][0] += ok
            totals[f][1] += n
        r = by_render[entry["render"]]
        r[0] += s["all_ok"]; r[1] += s["numbers_ok"]; r[2] += 1
        errors += bool(meta.get("error"))
        secs.append(meta.get("seconds", 0))
        tokens_in += meta.get("input_tokens", 0); tokens_out += meta.get("output_tokens", 0)
        models[meta.get("model", "-")] += 1
        rows.append({"invoice_id": entry["invoice_id"], "render": entry["render"], "layout": entry["layout"],
                     "all_ok": s["all_ok"], "numbers_ok": s["numbers_ok"], "model": meta.get("model"),
                     "seconds": meta.get("seconds"), "error": meta.get("error", ""), "mistakes": " | ".join(s["mistakes"])})
        flag = "OK  " if s["all_ok"] else "MISS"
        print(f"[{flag}] {entry['invoice_id']} {entry['render']:<5} {entry['layout']:<9} {meta.get('seconds', 0):>5}s  "
              + ("; ".join(s["mistakes"][:3]) + (" …" if len(s["mistakes"]) > 3 else "") if s["mistakes"] else ""))

    n = len(rows)
    all_ok = sum(r["all_ok"] for r in rows)
    nums_ok = sum(r["numbers_ok"] for r in rows)
    secs_sorted = sorted(secs)
    median = secs_sorted[n // 2] if n else 0

    lines = [
        f"# Extraction run: {args.label} ({args.set} set)",
        "",
        f"{n} invoices. Models used: {', '.join(f'{m} ({c})' for m, c in models.items())}. Failed calls: {errors}.",
        f"Median latency {median}s. Tokens: {tokens_in:,} in / {tokens_out:,} out.",
        "",
        "| | Invoices fully correct | All numbers correct |",
        "|---|---|---|",
        f"| **All** | **{all_ok}/{n} ({pct(all_ok, n)})** | **{nums_ok}/{n} ({pct(nums_ok, n)})** |",
        *[f"| {k} | {v[0]}/{v[2]} ({pct(v[0], v[2])}) | {v[1]}/{v[2]} ({pct(v[1], v[2])}) |" for k, v in sorted(by_render.items())],
        "",
        "| Field | Correct | Accuracy |",
        "|---|---|---|",
        *[f"| {f} | {totals[f][0]}/{totals[f][1]} | {pct(*totals[f])} |" for f in FIELD_ORDER if f in totals],
        "",
        "## Misses",
        "",
        *[f"- **{r['invoice_id']}** ({r['render']}, {r['layout']}): {r['error'] or r['mistakes']}" for r in rows if not r["all_ok"]],
    ]
    print("\n" + "\n".join(lines[:12 + len(by_render)]))

    if not args.self_test:
        out = ROOT / "docs" / "eval_runs"
        out.mkdir(parents=True, exist_ok=True)
        base = out / f"{datetime.now():%Y-%m-%d_%H%M}_extract_{args.set}_{args.label}"
        base.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nSaved {base.relative_to(ROOT)}.md/.csv")


if __name__ == "__main__":
    main()
