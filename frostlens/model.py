"""Steady NH3/CO2 cascade model using the CoolProp HEOS equation of state.

All public temperatures are deg C and all powers are kW. ``tm_c`` is the
CO2 condensing temperature, not a shared temperature for both refrigerants.
The heat-exchanger approach is Q_cascade / UA; no Carnot approximation is used.
"""
from functools import lru_cache
from threading import local

import CoolProp
from CoolProp import AbstractState, PSmass_INPUTS, QT_INPUTS
import numpy as np
from scipy import __version__ as scipy_version

KEYS = ("eta_low", "eta_high", "ua_kw_k", "aux_kw")
NAMES = ("低温级等熵效率", "高温级等熵效率", "复叠换热器等效 UA", "固定辅助功率")
LOWER = np.array([0.40, 0.40, 0.60, 0.00])
UPPER = np.array([0.90, 0.90, 6.00, 2.00])
SCALE = UPPER - LOWER
ENVELOPE = {"te_c": (-52.0, -20.0), "tc_c": (15.0, 50.0),
            "tm_c": (-18.0, 5.0), "load_kw": (0.5, 16.0)}
_states = local()


def _state(fluid):
    if not hasattr(_states, fluid):
        setattr(_states, fluid, AbstractState("HEOS", fluid))
    return getattr(_states, fluid)


@lru_cache(maxsize=65536)
def ideal_work_ratio(fluid, evaporating_c, condensing_c):
    """(h2s-h1)/(h1-h3), with saturated vapor suction and liquid outlet."""
    if not (-75 < evaporating_c < condensing_c < 100):
        raise ValueError("循环温度无法形成有效的蒸发—凝结过程。")
    state = _state(fluid)
    try:
        state.update(QT_INPUTS, 1.0, evaporating_c + 273.15)
        h1, s1 = state.hmass(), state.smass()
        state.update(QT_INPUTS, 0.0, condensing_c + 273.15)
        p_cond, h3 = state.p(), state.hmass()
        state.update(PSmass_INPUTS, p_cond, s1)
        h2s = state.hmass()
    except (ValueError, RuntimeError) as exc:
        raise ValueError("CoolProp 无法计算此工况的有效物性。") from exc
    q_evap = h1 - h3
    if q_evap <= 0 or h2s <= h1:
        raise ValueError("工况的制冷量或压缩功不是正数。")
    result = (h2s - h1) / q_evap
    if not np.isfinite(result):
        raise ValueError("物性计算产生了非有限值。")
    return float(result)


def point_prediction(point, parameters, derivative=False):
    """Return total, low-stage power and optionally physical-parameter Jacobian.

    Enthalpy ratios come directly from HEOS. Only the temperature derivative
    of the NH3 ratio is centered-differenced (0.001 K); other derivatives are
    analytic. This avoids rounding temperatures and corrupting fit derivatives.
    """
    eta_l, eta_h, ua, aux = np.asarray(parameters, dtype=float)
    te, tc, tm, load = (float(point[k]) for k in ("te_c", "tc_c", "tm_c", "load_kw"))
    ratio_l = ideal_work_ratio("CarbonDioxide", te, tm)
    wl = load * ratio_l / eta_l
    q_cascade = load + wl
    nh3_te = tm - q_cascade / ua
    if nh3_te <= -70 or nh3_te >= tc:
        raise ValueError("UA 对应的氨蒸发温度超出本模型范围（必须高于 −70°C）。")
    ratio_h = ideal_work_ratio("Ammonia", nh3_te, tc)
    wh = q_cascade * ratio_h / eta_h
    power = wl + wh + aux
    if not derivative:
        return float(power), float(wl)
    step = 1e-3
    dr_dt = (ideal_work_ratio("Ammonia", nh3_te + step, tc)
             - ideal_work_ratio("Ammonia", nh3_te - step, tc)) / (2 * step)
    dwl = -wl / eta_l
    jac = np.array([dwl + dwl * (ratio_h - q_cascade * dr_dt / ua) / eta_h,
                    -wh / eta_h,
                    q_cascade ** 2 * dr_dt / (eta_h * ua ** 2), 1.0])
    jac_low = np.array([dwl, 0.0, 0.0, 0.0])
    return float(power), float(wl), jac, jac_low


def metadata():
    return {"name": "NH₃/CO₂ 稳态复叠制冷 · HEOS 等效 UA 模型", "version": "0.1.0",
            "coolprop_version": CoolProp.__version__,
            "numpy_version": np.__version__, "scipy_version": scipy_version,
            "assumptions": [
                "CoolProp HEOS 真实流体物性；CO₂ 为低温级、NH₃ 为高温级。",
                "压缩机饱和蒸气吸气，冷凝器饱和液体出流；节流等焓；忽略压降、过热、过冷及外界热漏。",
                "tm 为 CO₂ 凝结温度；复叠换热量 Qc=Qload+Wlow，NH₃ 蒸发温度=tm−Qc/UA。",
                "两个等熵效率包含于热力学压缩功；默认电机效率为 1，固定辅助功率另计。真实电功率应用需校准或扩展电机模型。",
                "四个参数在全部测量期间恒定；输入温度与负荷视为准确，测量噪声按给定标准差独立、高斯处理。",
                "分项模式的总功率与低温级功率也假定噪声独立；同源电表或由分项相加得到总功率时通常不成立。",
                "局部可辨识性基于参数范围与测量噪声缩放后的 Jacobian，不是全局唯一性证明或置信区间。",
            ]}
