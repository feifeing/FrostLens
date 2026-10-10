"""Strict, unit-explicit data interchange. No spreadsheet execution or uploads."""

import csv
import hashlib
import io
import json

FIELDS = (
    "te_c", "tc_c", "tm_c", "load_kw", "power_kw", "sigma_kw",
    "low_power_kw", "sigma_low_kw",
)
REQUIRED = FIELDS[:6]
MAX_ROWS = 250


def read_csv(text):
    if not isinstance(text, str):
        raise ValueError("CSV 内容必须是文本。")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    names = reader.fieldnames or []
    if len(set(names)) != len(names):
        raise ValueError("CSV 有重复的列名。")
    missing = set(REQUIRED) - set(names)
    if missing:
        raise ValueError("CSV 缺少列：" + ", ".join(sorted(missing)))
    unknown = set(names) - set(FIELDS)
    if unknown:
        raise ValueError("CSV 包含未识别的列：" + ", ".join(sorted(unknown)))
    rows = []
    for line, raw in enumerate(reader, 2):
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"首版最多分析 {MAX_ROWS} 行，请先筛选稳定工况。")
        if None in raw:
            raise ValueError(f"CSV 第 {line} 行的列数超过表头。")
        row = {}
        for name, value in raw.items():
            if value is None or not value.strip():
                if name in REQUIRED:
                    raise ValueError(f"CSV 第 {line} 行的 {name} 不能为空。")
                continue
            try:
                row[name] = float(value)
            except ValueError as exc:
                raise ValueError(f"CSV 第 {line} 行的 {name} 必须为数值。") from exc
        rows.append(row)
    if not rows:
        raise ValueError("CSV 没有数据行。")
    return rows


def write_csv(rows):
    columns = [name for name in FIELDS if any(name in row for row in rows)]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def fingerprint(rows):
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
