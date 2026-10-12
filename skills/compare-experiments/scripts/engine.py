"""StateLens: explicit, auditable comparisons of experimental states (stdlib only).

Intervals describe sampling uncertainty under the declared design. They cannot
validate that design, remove confounding, or establish a causal mechanism.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from copy import deepcopy

VERSION = "0.2.0"
MAX_VALUES = 100_000
MAX_BOOTSTRAP_WORK = 30_000_000

# canonical value = observed value * scale + offset. No fuzzy unit inference.
UNITS = {
    "1": ("ratio", 1.0, 0.0),
    "fraction": ("ratio", 1.0, 0.0), "%": ("ratio", 0.01, 0.0),
    "s": ("time", 1.0, 0.0), "ms": ("time", 0.001, 0.0),
    "min": ("time", 60.0, 0.0), "h": ("time", 3600.0, 0.0),
    "W": ("power", 1.0, 0.0), "kW": ("power", 1000.0, 0.0),
    "Pa": ("pressure", 1.0, 0.0), "kPa": ("pressure", 1000.0, 0.0),
    "MPa": ("pressure", 1_000_000.0, 0.0),
    "m": ("length", 1.0, 0.0), "cm": ("length", 0.01, 0.0),
    "mm": ("length", 0.001, 0.0),
    "kg": ("mass", 1.0, 0.0), "g": ("mass", 0.001, 0.0),
    "mg": ("mass", 0.000001, 0.0),
    "K": ("temperature", 1.0, 0.0), "degC": ("temperature", 1.0, 273.15),
}


class ValidationError(ValueError):
    """Input cannot be interpreted safely under the StateLens contract."""


def _error(path, message):
    raise ValidationError(f"{path}: {message}")


def _number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _error(path, "expected a finite number, not a boolean or text")
    if abs(value) > 1e100 or not math.isfinite(value):
        _error(path, "number must be finite and have absolute value <= 1e100")
    return float(value)


def _text(value, path, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _error(path, f"expected nonempty text of at most {limit} characters")
    return value


def _list(value, path, maximum, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _error(path, f"expected an array containing {minimum}..{maximum} items")
    return value


def _object(value, path):
    if not isinstance(value, dict):
        _error(path, "expected an object")
    return value


def _json_check(value, path="input", depth=0, budget=None):
    """Validate unknown provenance fields too; reject non-JSON Python values."""
    if budget is None:
        budget = [1_000_000]
    budget[0] -= 1
    if budget[0] < 0 or depth > 24:
        _error(path, "JSON is too large or too deeply nested")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        _number(value, path)
    elif isinstance(value, str):
        if len(value) > 100_000:
            _error(path, "text exceeds 100000 characters")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _json_check(item, f"{path}[{i}]", depth + 1, budget)
    elif isinstance(value, dict):
        for key, item in value.items():
            _text(key, f"{path}.key")
            _json_check(item, f"{path}.{key}", depth + 1, budget)
    else:
        _error(path, "only JSON-compatible values are supported")


def _unique_texts(value, path):
    values = _list(value, path, 64)
    for i, item in enumerate(values):
        _text(item, f"{path}[{i}]", 200)
    if len(set(values)) != len(values):
        _error(path, "duplicate names are not allowed")
    return values


def _convert(value, source, destination, path):
    _text(source, path + ".unit", 100)
    if source == destination:
        return value
    if source not in UNITS or destination not in UNITS:
        _error(path, f"cannot convert unknown unit {source!r} to {destination!r}")
    a, b = UNITS[source], UNITS[destination]
    if a[0] != b[0]:
        _error(path, f"incompatible units {source!r} and {destination!r}")
    return (value * a[1] + a[2] - b[2]) / b[1]


def _prepare(data):
    _json_check(data)
    _object(data, "input")
    if data.get("schema_version") != "1.0":
        _error("schema_version", "expected '1.0'")
    title = _text(data.get("title", "StateLens comparison"), "title")
    raw_studies = _list(data.get("studies"), "studies", 32, 1)
    if "synthetic" in data and not isinstance(data["synthetic"], bool):
        _error("synthetic", "expected a boolean")
    if "sources" in data:
        for i, source in enumerate(_list(data["sources"], "sources", 1000)):
            _object(source, f"sources[{i}]")
    studies, study_ids, total = [], set(), 0
    for si, raw in enumerate(raw_studies):
        p = f"studies[{si}]"
        _object(raw, p)
        sid = _text(raw.get("id"), p + ".id", 200)
        if sid in study_ids:
            _error(p + ".id", "duplicate study id")
        study_ids.add(sid)
        design = raw.get("design", "descriptive")
        if design not in ("paired", "independent", "descriptive"):
            _error(p + ".design", "expected paired, independent, or descriptive")
        controls = _unique_texts(raw.get("context_keys", []), p + ".context_keys")
        varying = _unique_texts(raw.get("varying", []), p + ".varying")
        metrics, metric_ids = [], set()
        for mi, item in enumerate(_list(raw.get("metrics"), p + ".metrics", 64, 1)):
            mp = f"{p}.metrics[{mi}]"
            _object(item, mp)
            mid = _text(item.get("id"), mp + ".id", 200)
            if mid in metric_ids:
                _error(mp + ".id", "duplicate metric id")
            metric_ids.add(mid)
            direction = item.get("direction", "observe")
            if direction not in ("higher", "lower", "target", "observe"):
                _error(mp + ".direction", "unknown preference direction")
            margin = _number(item.get("margin", 0), mp + ".margin")
            if margin < 0:
                _error(mp + ".margin", "must be nonnegative")
            metric = {"id": mid, "label": _text(item.get("label", mid), mp + ".label"),
                      "unit": _text(item.get("unit", "1"), mp + ".unit", 100),
                      "direction": direction, "margin": margin}
            if direction == "target":
                metric["target"] = _number(item.get("target"), mp + ".target")
            metrics.append(metric)
        states, state_ids = [], set()
        for ti, item in enumerate(_list(raw.get("states"), p + ".states", 64, 2)):
            tp = f"{p}.states[{ti}]"
            _object(item, tp)
            tid = _text(item.get("id"), tp + ".id", 200)
            if tid in state_ids:
                _error(tp + ".id", "duplicate state id")
            state_ids.add(tid)
            context = _object(item.get("context", {}), tp + ".context")
            if len(context) > 128:
                _error(tp + ".context", "too many context fields")
            if any(isinstance(v, (dict, list)) for v in context.values()):
                _error(tp + ".context", "context values must be scalar")
            values, replicates = {m["id"]: {} for m in metrics}, set()
            for oi, observation in enumerate(_list(item.get("observations"), tp + ".observations", 5000)):
                op = f"{tp}.observations[{oi}]"
                _object(observation, op)
                rep = _text(observation.get("replicate"), op + ".replicate", 200)
                if rep in replicates:
                    _error(op + ".replicate", "duplicate replicate id within a state")
                replicates.add(rep)
                record = _object(observation.get("values"), op + ".values")
                units = _object(observation.get("units", {}), op + ".units")
                if set(record) - metric_ids or set(units) - metric_ids:
                    _error(op, "observation references an undeclared metric")
                total += len(metrics)
                if total > MAX_VALUES:
                    _error("studies", f"at most {MAX_VALUES} observation/metric slots are supported")
                for metric in metrics:
                    mid, unit = metric["id"], metric["unit"]
                    if mid in units:
                        _convert(0.0, units[mid], unit, op + "." + mid)
                    if record.get(mid) is not None:
                        values[mid][rep] = _convert(_number(record[mid], op + "." + mid),
                                                   units.get(mid, unit), unit, op + "." + mid)
            states.append({"id": tid, "label": _text(item.get("label", tid), tp + ".label"),
                           "context": deepcopy(context), "_values": values, "_replicates": replicates})
        baseline = _text(raw.get("baseline"), p + ".baseline", 200)
        if baseline not in state_ids:
            _error(p + ".baseline", "baseline must name an existing state")
        studies.append({"id": sid, "label": _text(raw.get("label", sid), p + ".label"),
                        "domain": _text(raw.get("domain", "unspecified"), p + ".domain"),
                        "question": _text(raw.get("question", title), p + ".question"),
                        "baseline": baseline, "design": design, "metrics": metrics,
                        "states": states, "context_keys": controls, "varying": varying})
    return title, studies


def _summary(values, unit):
    array = list(values.values())
    return {"n": len(array), "mean": statistics.fmean(array) if array else None,
            "sd": statistics.stdev(array) if len(array) > 1 else None,
            "min": min(array) if array else None, "max": max(array) if array else None, "unit": unit}


def _benefit(baseline, state, metric):
    direction = metric["direction"]
    if direction == "higher":
        return state - baseline
    if direction == "lower":
        return baseline - state
    if direction == "target":
        return abs(baseline - metric["target"]) - abs(state - metric["target"])
    return None


def _quantile(ordered, probability):
    position = (len(ordered) - 1) * probability
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def _bootstrap(a, b, paired, metric, draws, rng):
    out = []
    na, nb = len(a), len(b)
    # For a linear paired objective the mean of differences is algebraically
    # equivalent, but avoids cancellation from subtracting large group means.
    differences = ([_benefit(av, bv, metric) for av, bv in zip(a, b)]
                   if paired and metric["direction"] in ("higher", "lower") else None)
    for _ in range(draws):
        if paired:
            indices = [rng.randrange(na) for _ in range(na)]
            if differences is not None:
                out.append(statistics.fmean(differences[i] for i in indices))
                continue
            am = statistics.fmean(a[i] for i in indices)
            bm = statistics.fmean(b[i] for i in indices)
        else:
            am = statistics.fmean(a[rng.randrange(na)] for _ in range(na))
            bm = statistics.fmean(b[rng.randrange(nb)] for _ in range(nb))
        out.append(_benefit(am, bm, metric))
    out.sort()
    return [_quantile(out, 0.025), _quantile(out, 0.975)]


def _same_context(a, b):
    # JSON true and 1 are distinct controls; 1 and 1.0 represent the same value.
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _known_context(value):
    return value is not None and not (isinstance(value, str) and not value.strip())


def _gate(study, baseline, state):
    reasons, changes = [], []
    bc, sc = baseline["context"], state["context"]
    for key in study["context_keys"]:
        if not _known_context(bc.get(key)) or not _known_context(sc.get(key)):
            reasons.append(f"至少一个状态缺少必要条件 {key!r} 的有效记录。")
    for key in sorted(set(bc) | set(sc)):
        a, b = bc.get(key), sc.get(key)
        if key not in bc or key not in sc or not _same_context(a, b):
            allowed = key in study["varying"]
            changes.append({"key": key, "baseline": a, "state": b, "allowed": allowed})
            if not allowed:
                reasons.append(f"条件 {key!r} 发生变化，但未声明为本次实验有意改变的因素。")
    return ("blocked" if reasons else "comparable"), reasons, changes


def _metric_comparison(study, metric, baseline, state, gate, draws, seed, work):
    mid = metric["id"]
    ad, bd = baseline["_values"][mid], state["_values"][mid]
    shared = sorted(set(ad) & set(bd))
    am = statistics.fmean(ad.values()) if ad else None
    bm = statistics.fmean(bd.values()) if bd else None
    paired = study["design"] == "paired"
    complete = set(ad) == set(bd) and baseline["_replicates"] == state["_replicates"]
    result = {**metric, "baseline_mean": am, "state_mean": bm,
              "n_baseline": len(ad), "n_state": len(bd), "n_pairs": len(shared) if paired else None,
              "delta": bm - am if am is not None and bm is not None else None,
              "percent_delta": None, "benefit": None, "interval": None,
              "decision": "uncertain", "warnings": [], "sensitivity": {"positive_margin_max": None}}
    warnings = result["warnings"]
    if metric["unit"] not in UNITS:
        warnings.append("该单位未登记；仅按完全相同的单位文字处理，尚未独立核验量纲。")
    if len(ad) < len(baseline["_replicates"]) or len(bd) < len(state["_replicates"]):
        warnings.append("缺失值已排除，未用零填补；缺失原因可能使结果有偏。")
    if paired and not complete:
        warnings.append(f"配对不完整：有 {len(shared)} 对有效观测；"
                        f"另有 {len(set(ad) - set(bd))} 个仅基线有效、{len(set(bd) - set(ad))} 个仅当前状态有效的观测。"
                        "重复单元标识和有效值对应关系均须匹配，才计算区间。")
    if am is not None and bm is not None:
        result["benefit"] = _benefit(am, bm, metric)
        if paired and complete:
            result["delta"] = statistics.fmean(bd[k] - ad[k] for k in shared)
            if metric["direction"] in ("higher", "lower"):
                result["benefit"] = result["delta"] * (1 if metric["direction"] == "higher" else -1)
        if am > 0 and UNITS.get(metric["unit"], (None,))[0] != "temperature":
            percent = result["delta"] / am * 100.0
            if math.isfinite(percent):
                result["percent_delta"] = percent
            else:
                warnings.append("相对百分比变化超出有限数值范围，请使用绝对差值。")
        elif am <= 0:
            warnings.append("基线为零或负数，相对百分比变化无定义或容易误解，故不显示。")
        else:
            warnings.append("温度指标不显示相对百分比变化，请使用绝对温差。")
    if not study["context_keys"]:
        warnings.append("尚未声明必要的控制条件；结果仅作描述，是否可比仍待核实。")
    if gate == "blocked":
        result["decision"] = "blocked"
    elif am is None or bm is None:
        result["decision"] = "insufficient"
        warnings.append("至少一个状态在该指标上没有有效观测。")
    elif metric["direction"] == "observe" or study["design"] == "descriptive" or not study["context_keys"]:
        result["decision"] = "descriptive"
    elif paired and not complete:
        result["decision"] = "insufficient"
    elif min(len(ad), len(bd)) < 2:
        result["decision"] = "insufficient"
        warnings.append("每个状态至少需要两个有效观测，才能估算重采样区间。")
    else:
        cost = draws * (len(ad) + len(bd))
        if work[0] + cost > MAX_BOOTSTRAP_WORK:
            result["decision"] = "insufficient"
            warnings.append("已达到重采样计算量上限，请将数据拆分为更小的研究问题。")
            return result
        work[0] += cost
        a = [ad[k] for k in shared] if paired else sorted(ad.values())
        b = [bd[k] for k in shared] if paired else sorted(bd.values())
        # Stable per comparison, independent of traversal order and global RNG state.
        key = json.dumps([seed, study["id"], baseline["id"], state["id"], mid], ensure_ascii=False)
        rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest(), "big"))
        interval = _bootstrap(a, b, paired, metric, draws, rng)
        result["interval"] = interval
        lower, upper = interval
        if min(len(ad), len(bd)) < 5:
            result["decision"] = "insufficient"
            warnings.append("至少一个状态少于五个有效观测：区间仅供探索，不给出倾向判断。")
        else:
            margin = metric["margin"]
            result["decision"] = ("better" if lower > margin else "worse" if upper < -margin else
                                  "within_margin" if lower > -margin and upper < margin else "uncertain")
            if lower > 0:
                result["sensitivity"]["positive_margin_max"] = lower
        if len(set(a)) == 1 or len(set(b)) == 1:
            warnings.append("至少一个状态的观测值完全相同；重采样无法反映未观测波动或系统误差。")
    return result


def _pareto(study, comparisons):
    metrics = [m for m in study["metrics"] if m["direction"] != "observe"]
    note = ("基于观测均值的多指标权衡（Pareto）视图，未纳入联合不确定性；"
            "不能解释为优胜概率或因果结论。不可比、配对不完整或有缺失值的状态已排除。")
    if not metrics or not study["context_keys"]:
        return {"state_ids": [], "eligible_ids": [], "note": "未声明指标偏好或必要控制条件，因此不提供权衡排序。"}
    baseline = next(s for s in study["states"] if s["id"] == study["baseline"])
    comparison_by_id = {c["state_id"]: c for c in comparisons}
    eligible, vectors = [], {}
    for state in study["states"]:
        if any(not _known_context(state["context"].get(k)) for k in study["context_keys"]):
            continue
        if state["id"] != study["baseline"] and comparison_by_id[state["id"]]["gate"] != "comparable":
            continue
        if any(not state["_values"][m["id"]] or
               len(state["_values"][m["id"]]) != len(state["_replicates"]) for m in metrics):
            continue
        if study["design"] == "paired" and (
                state["_replicates"] != baseline["_replicates"] or
                any(set(state["_values"][m["id"]]) != set(baseline["_values"][m["id"]]) for m in metrics)):
            continue
        eligible.append(state["id"])
        vectors[state["id"]] = [_benefit(0.0, statistics.fmean(state["_values"][m["id"]].values()), m) for m in metrics]
    frontier = [sid for sid in eligible if not any(
        all(a >= b for a, b in zip(vectors[other], vectors[sid])) and
        any(a > b for a, b in zip(vectors[other], vectors[sid]))
        for other in eligible if other != sid)]
    return {"state_ids": frontier, "eligible_ids": eligible, "note": note}


def compare_dataset(data, draws=2000, seed=1729):
    """Validate a schema 1.0 dataset and return a deterministic JSON-safe report.

    Inputs are never mutated. Bootstrap draws must be 100..10000; uncertainty
    intervals are marginal 95% percentile intervals, without multiplicity correction.
    """
    if isinstance(draws, bool) or not isinstance(draws, int) or not 100 <= draws <= 10_000:
        _error("draws", "expected an integer from 100 to 10000")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**63 - 1:
        _error("seed", "expected an integer from 0 to 2^63-1")
    title, studies = _prepare(data)
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    provenance = {"engine_version": VERSION, "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                  "seed": seed, "draws": draws,
                  "method": "按声明的配对或独立设计进行百分位重采样，估计目标导向均值收益的边际 95% 区间。",
                  "limitations": ["仅检查已记录条件；无法核验未记录混杂因素、因果关系和测量准确性。",
                                  "重复观测须对应独立抽样单元；时间相关或嵌套设计需要专门模型。",
                                  "区间未经多重比较校正，结果用于探索，不能替代确证性假设检验。",
                                  "缺失观测已排除；未登记单位仅在文字完全相同时接受。",
                                  "目标值收益比较组均值离目标的距离，而非每次观测离目标距离的平均值。",
                                  "超过实际意义阈值使用严格不等式；positive_margin_max 表示不能取到的上限。"]}
    if "sources" in data:
        provenance["sources"] = deepcopy(data["sources"])
    if "synthetic" in data:
        provenance["synthetic"] = data["synthetic"]
    report = {"schema_version": "statelens-report/1", "title": title, "provenance": provenance, "studies": []}
    work = [0]
    for study in studies:
        baseline = next(s for s in study["states"] if s["id"] == study["baseline"])
        comparisons = []
        for state in study["states"]:
            if state["id"] == baseline["id"]:
                continue
            gate, reasons, changes = _gate(study, baseline, state)
            comparisons.append({"state_id": state["id"], "baseline_id": baseline["id"], "gate": gate,
                                "reasons": reasons, "changes": changes,
                                "metrics": [_metric_comparison(study, metric, baseline, state, gate, draws, seed, work)
                                            for metric in study["metrics"]]})
        next_steps = []
        if not study["context_keys"]:
            next_steps.append("先补充必要控制条件，并说明哪些因素是实验有意改变的，再解释差异。")
        if any(c["gate"] == "blocked" for c in comparisons):
            next_steps.append("先补齐缺失条件，或确认未声明的条件变化，暂不据此判断哪个状态更好。")
        if any(m["decision"] == "insufficient" for c in comparisons for m in c["metrics"]):
            next_steps.append("增加独立重复观测或补齐配对，并检查缺失原因，再估算不确定性。")
        if study["design"] == "descriptive":
            next_steps.append("仅在实验设计确实支持时，才声明配对或独立抽样。")
        if any(m["direction"] == "observe" for m in study["metrics"]):
            next_steps.append("依据研究问题明确指标方向和实际意义阈值；没有依据时保留描述性比较。")
        next_steps.append("核对数据来源、单位和抽样假设，并用后续实验检验当前解释。")
        public = {key: study[key] for key in ("id", "label", "domain", "question", "baseline", "design", "context_keys", "varying", "metrics")}
        public["states"] = [{"id": s["id"], "label": s["label"], "context": s["context"],
                             "summary": {m["id"]: _summary(s["_values"][m["id"]], m["unit"]) for m in study["metrics"]}}
                            for s in study["states"]]
        public.update(comparisons=comparisons, pareto=_pareto(study, comparisons), next_steps=next_steps)
        report["studies"].append(public)
    # Guarantee finite output even for extreme but accepted inputs.
    try:
        json.dumps(report, allow_nan=False)
    except (ValueError, OverflowError) as exc:
        raise ValidationError("Computed result exceeds finite numeric limits; rescale input values.") from exc
    return report
