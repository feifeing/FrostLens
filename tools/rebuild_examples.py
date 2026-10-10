"""Regenerate all public examples from the actual inference code (synthetic only)."""
from pathlib import Path
import json
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frostlens.core import catalog, case_rows
from frostlens.io import write_csv
from frostlens.server import build_report


def main():
    examples = ROOT / "examples"
    examples.mkdir(exist_ok=True)
    reports = {}
    for case in catalog():
        name = case["id"]
        rows = case_rows(name)
        start = perf_counter()
        reports[name] = build_report(rows, case_id=name)
        print(f"{name}: {perf_counter() - start:.3f}s; {reports[name]['summary']}")
        (examples / f"{name}.csv").write_text(write_csv(rows), encoding="utf-8", newline="")
        (examples / f"{name}-report.json").write_text(json.dumps(reports[name], ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    bundle = {"cases": catalog(), "report": reports["narrow"], "reports": reports}
    content = "// Computed synthetic examples. Rebuild with python tools/rebuild_examples.py\nwindow.FROSTLENS_DEMO = " + json.dumps(bundle, ensure_ascii=False, allow_nan=False) + ";\n"
    (ROOT / "frostlens" / "web" / "demo-data.js").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
