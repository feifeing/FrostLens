"""Inference, alternative-explanation search and sequential experiment design."""
import hashlib
import json
from itertools import product
from math import isfinite
from numbers import Real

import numpy as np
from scipy.optimize import least_squares

from .model import ENVELOPE, KEYS, LOWER, NAMES, SCALE, UPPER, metadata, point_prediction

DEFAULT_BOUNDS = {"te_c": [-48.0, -28.0], "tc_c": [24.0, 44.0],
                  "tm_c": [-15.0, 2.0], "load_kw": [4.0, 14.0]}
TRUE_PARAMETERS = np.array([0.70, 0.74, 1.80, 0.35])
DISPLAY_DELTA_SSE = 3.84


def catalog():
    return [
        {"id": "narrow", "name": "同样吻合，两种解释", "description": "相近工况的 12 次测量：拟合可以很好，参数仍可能难以区分。", "synthetic": True},
        {"id": "wide", "name": "让工况提供更多线索", "description": "覆盖不同温度和负荷的 16 次测量，比较激励范围与分项传感器的作用。", "synthetic": True},
        {"id": "drift", "name": "模型也可能解释不了", "description": "显式模型外案例：低温级效率随测量序号下降，检验恒参数假设。", "synthetic": True},
    ]


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise ValueError(f"{label} 必须是有限数值。")
    return float(value)


def _point(point, label="工况"):
    if not isinstance(point, dict):
        raise ValueError(f"{label} 必须是包含温度和负荷的对象。")
    result = {}
    for key, (lo, hi) in ENVELOPE.items():
        if key not in point:
            raise ValueError(f"{label} 缺少 {key}。")
        v = _number(point[key], f"{label} {key}")
        if not lo <= v <= hi:
            raise ValueError(f"{label} {key} 必须在 [{lo:g}, {hi:g}] 内。")
        result[key] = v
    if result["tm_c"] - result["te_c"] < 8:
        raise ValueError(f"{label} 的 CO₂ 凝结温度需至少高于蒸发温度 8°C。")
    if result["tc_c"] - result["tm_c"] < 12:
        raise ValueError(f"{label} 的 NH₃ 凝结温度需至少高于 CO₂ 凝结温度 12°C。")
    return result


def validate_rows(rows, sensor_mode="power"):
    if sensor_mode not in ("power", "split"):
        raise ValueError("传感器模式必须为 power 或 split。")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 250:
        raise ValueError("测量数据必须包含 1–250 行。")
    cleaned = []
    for i, row in enumerate(rows):
        label = f"第 {i + 1} 行"
        out = _point(row, label)
        required = ("power_kw", "sigma_kw") + (("low_power_kw", "sigma_low_kw") if sensor_mode == "split" else ())
        for key in required:
            if key not in row:
                raise ValueError(f"{label} 缺少 {key}。")
        for key in ("power_kw", "sigma_kw", "low_power_kw", "sigma_low_kw"):
            if key in row:
                out[key] = _number(row[key], f"{label} {key}")
                lower = 1e-6 if key.startswith("sigma") else 0
                if not lower < out[key] <= 10000:
                    raise ValueError(f"{label} {key} 需大于 {lower:g} 且不超过 10000。")
        if "low_power_kw" in out and out["low_power_kw"] >= out["power_kw"]:
            raise ValueError(f"{label} 低温级功率应小于总功率，请检查单位或测量数据。")
        cleaned.append(out)
    return cleaned


def _case_points(case_id):
    if case_id == "narrow":
        return [{"te_c": -40 + 0.12 * np.sin(i), "tc_c": 35 + 0.15 * np.cos(i * 1.7),
                 "tm_c": -8 + 0.08 * np.sin(i * 2.1), "load_kw": 8 + 0.04 * np.cos(i * 1.3)} for i in range(12)]
    if case_id in ("wide", "drift"):
        settings = [(-48, 24, -15, 4), (-28, 44, 2, 14), (-48, 44, 2, 4), (-28, 24, -15, 14),
                    (-48, 24, 2, 14), (-28, 44, -15, 4), (-48, 44, -15, 14), (-28, 24, 2, 4),
                    (-40, 34, -7, 9), (-48, 34, -7, 14), (-28, 34, -7, 4), (-38, 44, 2, 9),
                    (-38, 24, -15, 9), (-44, 40, -12, 6), (-32, 28, -3, 12), (-40, 36, -8, 8)]
        return [dict(zip(("te_c", "tc_c", "tm_c", "load_kw"), values)) for values in settings]
    raise ValueError("未知合成案例；请选择 narrow、wide 或 drift。")


def virtual_measurement(case_id, point, index=0):
    _case_points(case_id)
    point = _point(point)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 10000:
        raise ValueError("合成测量序号必须为 0–10000 的整数。")
    parameters = TRUE_PARAMETERS.copy()
    if case_id == "drift":
        parameters[0] = 0.74 - 0.22 * min(index / 15, 1)
    total, low = point_prediction(point, parameters)
    seed_text = json.dumps([case_id, point, index], sort_keys=True, separators=(",", ":"))
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    # Independent noise is intentional and matches the weighting in this demo.
    sigma, sigma_low = 0.045, 0.025
    return {**point, "power_kw": float(total + rng.normal(0, sigma)), "sigma_kw": sigma,
            "low_power_kw": float(low + rng.normal(0, sigma_low)), "sigma_low_kw": sigma_low}


def case_rows(case_id):
    return [virtual_measurement(case_id, point, i) for i, point in enumerate(_case_points(case_id))]


class _Fit:
    def __init__(self, rows, mode):
        self.rows, self.mode = rows, mode
        self.last_x = self.last_value = None

    def evaluate(self, x):
        if self.last_x is not None and np.array_equal(self.last_x, x):
            return self.last_value
        p = LOWER + SCALE * x
        residual, jac = [], []
        for row in self.rows:
            total, low, jt, jl = point_prediction(row, p, derivative=True)
            residual.append((total - row["power_kw"]) / row["sigma_kw"])
            jac.append(jt * SCALE / row["sigma_kw"])
            if self.mode == "split":
                residual.append((low - row["low_power_kw"]) / row["sigma_low_kw"])
                jac.append(jl * SCALE / row["sigma_low_kw"])
        value = np.array(residual), np.array(jac)
        self.last_x, self.last_value = np.array(x, copy=True), value
        return value

    def residual(self, x):
        return self.evaluate(x)[0]

    def jacobian(self, x):
        return self.evaluate(x)[1]


def _solve(fit):
    starts = [np.array([0.6, 0.6, 0.25, 0.2]), np.array([0.2, 0.8, 0.75, 0.05]),
              np.array([0.85, 0.25, 0.1, 0.6])]
    full_solutions = []
    for start in starts:
        result = least_squares(fit.residual, start, jac=fit.jacobian, bounds=(0, 1),
                               max_nfev=120, ftol=1e-9, xtol=1e-9, gtol=1e-8)
        full_solutions.append((float(result.fun @ result.fun), result.x.copy(), "multistart", bool(result.success)))
    best = min(full_solutions, key=lambda item: item[0])
    _, _, vh = np.linalg.svd(fit.jacobian(best[1]), full_matrices=False)
    fixed = int(np.argmax(np.abs(vh[-1])))
    free = [i for i in range(4) if i != fixed]
    profiles = []
    for fixed_value in (0.03, 0.32, 0.65, 0.97):
        def expand(z):
            full = best[1].copy()
            full[fixed], full[free] = fixed_value, z
            return full
        result = least_squares(lambda z: fit.residual(expand(z)), best[1][free],
                               jac=lambda z: fit.jacobian(expand(z))[:, free], bounds=(0, 1),
                               max_nfev=100, ftol=1e-9, xtol=1e-9, gtol=1e-8)
        profiles.append((float(result.fun @ result.fun), expand(result.x), "bounded_profile", bool(result.success)))
    # A converged three-variable profile is not a converged four-variable fit.
    # If it discovers a better basin, release the fixed coordinate before it
    # can replace the reported optimum. Retain profiles as alternative evidence.
    for profile in sorted(profiles, key=lambda item: item[0]):
        if profile[0] >= best[0]:
            break
        result = least_squares(fit.residual, profile[1], jac=fit.jacobian, bounds=(0, 1),
                               max_nfev=120, ftol=1e-9, xtol=1e-9, gtol=1e-8)
        polished = (float(result.fun @ result.fun), result.x.copy(), "profile_polish", bool(result.success))
        full_solutions.append(polished)
        best = min(full_solutions, key=lambda item: item[0])
    alternatives = [item for item in full_solutions + profiles
                    if item[0] <= best[0] + DISPLAY_DELTA_SSE and np.linalg.norm(item[1] - best[1]) / 2 >= 0.12]
    alternative = max(alternatives, key=lambda item: np.linalg.norm(item[1] - best[1])) if alternatives else None
    return best, alternative


def _bounds(bounds):
    if bounds is None:
        return {key: list(value) for key, value in DEFAULT_BOUNDS.items()}
    if not isinstance(bounds, dict) or set(bounds) - set(ENVELOPE):
        raise ValueError("实验范围只接受 te_c、tc_c、tm_c、load_kw 四个字段。")
    result = {}
    for key, default in DEFAULT_BOUNDS.items():
        values = bounds.get(key, default)
        if not isinstance(values, (list, tuple)) or len(values) != 2:
            raise ValueError(f"{key} 的实验范围必须为 [下限, 上限]。")
        lo, hi = (_number(v, f"{key} 实验范围") for v in values)
        if not ENVELOPE[key][0] <= lo <= hi <= ENVELOPE[key][1]:
            raise ValueError(f"{key} 的实验范围需位于 {ENVELOPE[key]} 内且下限不大于上限。")
        result[key] = [lo, hi]
    return result


def _diagnostics(jac):
    _, singular, vh = np.linalg.svd(jac, full_matrices=False)
    s0 = float(singular[0]) if len(singular) else 0
    smallest = float(singular[-1])
    condition = s0 / smallest if smallest > max(s0 * 1e-12, 1e-12) else None
    return singular, vh[-1], condition


def _design(rows, mode, p, alt, jac, budget, bounds):
    sigma = float(np.median([row["sigma_kw"] for row in rows]))
    sigma_low = float(np.median([row["sigma_low_kw"] for row in rows])) if mode == "split" else None
    keys = tuple(DEFAULT_BOUNDS)
    axes = [np.unique(np.linspace(*bounds[key], 3)) for key in keys]
    candidates = []
    for values in product(*axes):
        point = dict(zip(keys, map(float, values)))
        try:
            _point(point)
            pred, low, jt, jl = point_prediction(point, p, derivative=True)
            alt_pred, alt_low = point_prediction(point, alt) if alt is not None else (None, None)
            jc = np.array([jt * SCALE / sigma] + ([jl * SCALE / sigma_low] if mode == "split" else []))
            sep = float(np.hypot((pred - alt_pred) / sigma, (low - alt_low) / sigma_low if mode == "split" else 0)) if alt is not None else None
            candidates.append({"point": point, "predicted_kw": pred, "alternative_kw": alt_pred,
                               "separation_sigma": sep, "channel": mode, "_jac": jc})
        except ValueError:
            continue
    candidate_count = len(candidates)
    ridge = 1e-6
    accumulated_jac = jac.copy()
    selected = []
    for order in range(min(budget, candidate_count)):
        _, information_singular, directions = np.linalg.svd(accumulated_jac, full_matrices=False)
        for item in candidates:
            j = item["_jac"]
            # SVD evaluates the matrix-determinant lemma without forming J'J.
            # An absolute ridge can disappear in J'J at very small sensor noise.
            whitened = (j @ directions.T) / np.sqrt(information_singular ** 2 + ridge)
            added_singular = np.linalg.svd(whitened, compute_uv=False)
            item["_gain"] = float(np.log1p(added_singular ** 2).sum())
        chosen = max(candidates, key=lambda item: item["_gain"])
        candidates.remove(chosen)
        before = float(information_singular[-1])
        accumulated_jac = np.vstack((accumulated_jac, chosen["_jac"]))
        after = float(np.linalg.svd(accumulated_jac, compute_uv=False)[-1])
        selected.append({**{key: value for key, value in chosen.items() if not key.startswith("_")},
                         "rank": order + 1, "gain": chosen["_gain"],
                         "smallest_singular_before": before, "smallest_singular_after": after})
    return selected, {"criterion": "顺序局部 D-optimal：最大化 log det 信息矩阵增量", "ridge": ridge,
                      "candidate_count": candidate_count, "bounds": bounds,
                      "prospective_sigma_kw": sigma, "prospective_sigma_low_kw": sigma_low,
                      "note": "在用户范围内每个输入取最多 3 个值并筛除无效物性；逐点更新当前最优模型的局部信息矩阵。未来噪声使用当前标准差的中位数。预测差/噪声是模型间差异，并非保证可区分的概率。"}


def analyze(rows, sensor_mode="power", budget=3, bounds=None):
    rows = validate_rows(rows, sensor_mode)
    if len(rows) < 4:
        raise ValueError("拟合四个参数至少需要 4 行；建议更多独立工况。")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 5:
        raise ValueError("实验预算必须为 1–5 的整数。")
    bounds = _bounds(bounds)
    fit = _Fit(rows, sensor_mode)
    best, alternate = _solve(fit)
    sse, x, source, converged = best
    parameters = LOWER + SCALE * x
    residual, jac = fit.evaluate(x)
    singular, weak, condition = _diagnostics(jac)
    effective_rank = int(np.sum(singular >= 1.0))
    numerical_threshold = float(singular[0] * max(jac.shape) * np.finfo(float).eps)
    numerical_rank = int(np.sum(singular > numerical_threshold))
    weighted_rmse = float(np.sqrt(np.mean(residual ** 2)))
    alt_parameters = LOWER + SCALE * alternate[1] if alternate is not None else None
    predictions = []
    for row in rows:
        predicted, low = point_prediction(row, parameters)
        alt_pred = point_prediction(row, alt_parameters)[0] if alternate is not None else None
        predictions.append({"observed_kw": row["power_kw"], "fitted_kw": predicted,
                            "alternative_kw": alt_pred, "residual_kw": row["power_kw"] - predicted,
                            "fitted_low_power_kw": low})
    rmse = float(np.sqrt(np.mean([p["residual_kw"] ** 2 for p in predictions])))
    status = "mismatch" if weighted_rmse > 2.5 else ("informative" if effective_rank == 4 else "weak")
    messages = {"weak": "总功率可以吻合，但部分参数方向仍缺少信息；下一次测量应主动改变工况。",
                "informative": "在当前模型、噪声与参数尺度下，四个局部参数方向均有信息；这不证明全局唯一。",
                "mismatch": "残差明显超过给定测量噪声；请先检查噪声估计、数据质量和恒参数模型假设。"}
    warnings = ["全部推断依赖理想稳态循环；本工具不构成设备故障确诊。", "输入温度和负荷误差尚未传播，参数界限会影响可辨识性指标。"]
    if status == "mismatch":
        warnings.append("加权残差 RMS > 2.5；此阈值仅作模型检查提示，不能单凭残差确定故障原因。当前实验设计仍以该模型为条件。")
    if sensor_mode == "split":
        warnings.append("总功率与低温级功率按独立噪声计算；若来自同一电表或总功率由分项求和，相关性会夸大信息增益，请勿据此宣称增加了独立信息。")
    if condition is None:
        warnings.append("最小奇异值接近数值零，条件数以 null 表示，不能解释为零。")
    if np.any((x < 0.001) | (x > 0.999)):
        warnings.append("至少一个参数贴近设定边界；它可能反映信息不足、噪声或模型失配。")
    if not converged:
        warnings.append("最优候选达到迭代预算但未满足收敛判据；数值结果需谨慎解释。")
    design, design_meta = _design(rows, sensor_mode, parameters, alt_parameters, jac, budget, bounds)
    if not design:
        warnings.append("指定范围内没有满足温差和物性约束的实验点，请调整实验范围。")
    alternative = None
    if alternate is not None:
        alt_res = [(row["power_kw"] - point_prediction(row, alt_parameters)[0]) for row in rows]
        alternative = {"parameters": dict(zip(KEYS, map(float, alt_parameters))),
                       "rmse_kw": float(np.sqrt(np.mean(np.square(alt_res)))),
                       "weighted_rmse": float(np.sqrt(alternate[0] / len(residual))),
                       "distance": float(np.linalg.norm(alternate[1] - x) / 2),
                       "search_method": alternate[2], "delta_sse": float(alternate[0] - sse),
                       "note": "显示阈值：加权 SSE 不高于最优解 +3.84，且参数范围归一化距离≥0.12；这是候选筛选规则，不是置信区间。"}
    return {"model": metadata(), "rows": rows, "sensor_mode": sensor_mode, "budget": budget,
            "fit": {"weighted_sse": sse, "residual_count": len(residual),
                    "search_method": source, "converged": converged},
            "summary": {"n": len(rows), "rmse_kw": rmse, "weighted_rmse": weighted_rmse,
                        "rank": effective_rank, "numerical_rank": numerical_rank,
                        "condition": condition, "status": status, "message": messages[status]},
            "parameters": [{"key": key, "name": name, "value": float(value), "unit": unit,
                            "lower": float(lo), "upper": float(hi)} for key, name, value, unit, lo, hi
                           in zip(KEYS, NAMES, parameters, ("", "", "kW/K", "kW"), LOWER, UPPER)],
            "alternative": alternative, "predictions": predictions,
            "identifiability": {"singular_values": list(map(float, singular)),
                                "relative_singular_values": list(map(float, singular / singular[0])),
                                "effective_direction_threshold": 1.0,
                                "numerical_rank_threshold": numerical_threshold,
                                "parameter_scales": dict(zip(KEYS, map(float, SCALE))),
                                "weak_direction": [{"name": name, "weight": float(weight)} for name, weight in zip(NAMES, weak)],
                                "explanation": "Jacobian 按各参数完整边界宽度和各观测标准差缩放。有效秩为奇异值≥1的方向数：单位参数尺度变化产生至少单位噪声尺度响应。最弱方向是局部组合变化，符号可整体翻转。该阈值是描述性尺度，不是显著性检验。"},
            "design": design, "design_meta": design_meta, "warnings": warnings}
