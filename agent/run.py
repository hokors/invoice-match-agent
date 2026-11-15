"""Run the agent: read invoices, 3-way match them, create draft vendor bills in Odoo.

    python -m agent.run inbox/                      # every PDF/JPG/PNG in a folder, oldest name first
    python -m agent.run invoice.pdf --dry-run       # show the match report, write nothing
    python -m agent.run --remove-drafts             # delete draft bills the agent created (sandbox reset)

Nothing is ever posted or paid. Bills are drafts for a person to review in Odoo.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import OdooContext
from .extract import Extractor
from .gemini import Gemini, GeminiError
from .matching import Matcher
from .odoo import Odoo
from .writeback import BillWriter, remove_agent_drafts

SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}


def collect(paths: list[str]) -> list[Path]:
    files = []
    for p in map(Path, paths):
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in SUFFIXES) if p.is_dir() else [p]
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--dry-run", action="store_true", help="don't write anything to Odoo")
    ap.add_argument("--extractions", help="reuse cached extractions from data/extractions/<set>/<label>/ (matched by file name)")
    ap.add_argument("--models", nargs="+", default=["gemini-flash-lite-latest", "gemini-flash-latest"])
    ap.add_argument("--remove-drafts", action="store_true")
    args = ap.parse_args()

    odoo = Odoo.from_env()
    if args.remove_drafts:
        print(f"Removed {remove_agent_drafts(odoo)} agent-created draft bills.")
        return

    ctx = OdooContext(odoo)
    matcher = Matcher(ctx)
    writer = None if args.dry_run else BillWriter(odoo, ctx)
    extractor = None if args.extractions else Extractor(Gemini.from_env(args.models))

    counts = {"ready": 0, "needs_review": 0}
    for file in collect(args.paths):
        if args.extractions:
            cached = Path(args.extractions) / f"{file.stem}.json"
            inv = json.loads(cached.read_text(encoding="utf-8"))["extraction"] if cached.exists() else {}
        else:
            try:
                inv, _ = extractor.extract(file)
            except GeminiError as e:
                print(f"  (extraction failed: {e})")
                inv = {}
        report = matcher.match(inv)
        counts[report["status"]] += 1
        bill = writer.write(inv, report, file) if writer else None
        print(f"{file.name:<18} {report['status']:<13} PO {report.get('po') or '-':<7} "
              f"{'bill #' + str(bill) if bill else '(dry run)'}")
        for issue in report["issues"]:
            print(f"    - {issue['message']}")
    print(f"\n{counts['ready']} ready for approval, {counts['needs_review']} need review."
          + ("" if args.dry_run else " Draft bills created in Odoo; nothing was posted or paid."))


if __name__ == "__main__":
    main()
