"""Render a portable StateLens report, without third-party dependencies."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_report(report: dict[str, Any]) -> str:
    """Return a self-contained report; embedded input can never close its script.

    Strict JSON deliberately rejects NaN and infinity instead of rendering a
    report whose numerical meaning would differ between Python and JavaScript.
    All report strings are subsequently placed in the DOM with textContent.
    """
    serialized = json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    serialized = (serialized.replace("&", "\\u0026")
                  .replace("<", "\\u003c")
                  .replace(">", "\\u003e")
                  .replace("\u2028", "\\u2028")
                  .replace("\u2029", "\\u2029"))
    template = (Path(__file__).resolve().parent.parent / "assets" / "report.html").read_text(encoding="utf-8")
    marker = "__STATELENS_REPORT_JSON__"
    if template.count(marker) != 1:
        raise ValueError("StateLens report template must contain exactly one data marker")
    return template.replace(marker, serialized)
