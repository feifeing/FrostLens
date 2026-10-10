"""Reproduce the three-step synthetic experiment demonstration."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from frostlens.core import analyze, case_rows, virtual_measurement

rows = case_rows("narrow")
trace = []
for step in range(4):
    report = analyze(rows)
    summary = report["summary"]
    trace.append({"step": step, "n": len(rows), "effective_directions": summary["rank"],
                  "condition": summary["condition"], "rmse_kw": summary["rmse_kw"],
                  "smallest_singular_value": report["identifiability"]["singular_values"][-1]})
    if step < 3:
        point = report["design"][0]["point"]
        rows.append(virtual_measurement("narrow", point, index=len(rows)))
result = {"kind": "synthetic", "policy": "Re-fit after each new observation; select first current recommendation.",
          "model": report["model"], "trace": trace}
(ROOT / "examples" / "sequence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps(trace, indent=2))
