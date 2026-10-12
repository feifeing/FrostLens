"""Rebuild fictional, deterministic StateLens examples (no scientific measurements)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills" / "compare-experiments" / "assets"


def make_study(sid, label, domain, question, metrics, contexts, means, noise, design="paired"):
    states = []
    offsets = [-1.1, .4, .8, -.6, 1.0, -.2, .3, -.6]
    for index, (state_id, state_label, context) in enumerate(contexts):
        observations = []
        for i, offset in enumerate(offsets):
            values = {m["id"]:round(means[index][j] + noise[j] * (offset + index * ((i % 3) - 1) * .12), 5)
                      for j, m in enumerate(metrics)}
            observations.append({"replicate":f"unit-{i+1}", "values":values, "source_id":"synthetic-generator",
                                 "locator":f"{sid}/{state_id}/unit-{i+1}"})
        states.append({"id":state_id, "label":state_label, "context":context, "observations":observations})
    return {"id":sid, "label":label, "domain":domain, "question":question, "baseline":states[0]["id"],
            "design":design, "context_keys":[k for k in contexts[0][2] if k != "treatment"],
            "varying":["treatment"], "metrics":metrics, "states":states}


def metric(mid, label, unit, direction, margin, **extra):
    return dict(id=mid, label=label, unit=unit, direction=direction, margin=margin, **extra)


def main():
    studies = [
        make_study("computing", "快一点，还是更准确？", "计算机科学", "相同测试集与硬件下，缓存和量化分别改变什么？",
                   [metric("latency", "响应时间", "ms", "lower", 3), metric("accuracy", "准确率", "%", "higher", .5)],
                   [("baseline", "原始模型", {"hardware":"CPU-A", "testset":"fixed-v1", "treatment":"baseline"}),
                    ("cache", "增加缓存", {"hardware":"CPU-A", "testset":"fixed-v1", "treatment":"cache"}),
                    ("quantized", "轻量量化", {"hardware":"CPU-A", "testset":"fixed-v1", "treatment":"quantized"})],
                   [[52,94],[43,94.1],[31,91.8]], [3,.35]),
        make_study("materials", "更强，也更重？", "材料科学", "相同测试协议下，强化方案如何改变强度和质量？",
                   [metric("strength", "拉伸强度", "MPa", "higher", 10), metric("mass", "试样质量", "g", "lower", .5)],
                   [("baseline", "原始材料", {"protocol":"tensile-v1", "batch":"B-1", "treatment":"raw"}),
                    ("reinforced", "强化方案", {"protocol":"tensile-v1", "batch":"B-1", "treatment":"reinforced"}),
                    ("hot_test", "换了测试协议", {"protocol":"hot-tensile-v2", "batch":"B-1", "treatment":"reinforced"})],
                   [[220,10],[250,11.4],[290,11.3]], [8,.15], "independent"),
        make_study("chemistry", "接近目标，值得多少能耗？", "化学实验", "在同批原料下，反应温度能否更接近目标并降低能耗？",
                   [metric("temperature", "稳态温度", "degC", "target", .5, target=60),
                    metric("energy", "平均输入功率", "W", "lower", 5)],
                   [("baseline", "原始控制", {"feedstock":"lot-A", "duration":"30min", "treatment":"baseline"}),
                    ("adaptive", "自适应控制", {"feedstock":"lot-A", "duration":"30min", "treatment":"adaptive"}),
                    ("low_power", "低功率控制", {"feedstock":"lot-A", "duration":"30min", "treatment":"low-power"})],
                   [[64,120],[60.5,108],[57,91]], [.4,2]),
        make_study("thermal", "相同负荷，真正改善了吗？", "热流工程", "同一负荷与边界温度下，改造方案的功率和稳定性如何变化？",
                   [metric("power", "输入功率", "kW", "lower", .1), metric("settling", "稳定时间", "s", "lower", 5)],
                   [("baseline", "原始系统", {"load":"8kW", "ambient":"25degC", "treatment":"baseline"}),
                    ("retuned", "重新整定", {"load":"8kW", "ambient":"25degC", "treatment":"retuned"}),
                    ("light_load", "降低了负荷", {"load":"6kW", "ambient":"25degC", "treatment":"retuned"})],
                   [[4.5,80],[4.18,91],[3.5,64]], [.08,3])
    ]
    # Exercise actual unit conversion, not merely label changes.
    for row in studies[0]["states"][1]["observations"]:
        row["values"]["latency"] /= 1000
        row["units"] = {"latency":"s"}
    for row in studies[2]["states"][1]["observations"]:
        row["values"]["temperature"] += 273.15
        row["units"] = {"temperature":"K"}
    data = {"schema_version":"1.0", "title":"StateLens · 四个领域，一种比较语言", "synthetic":True,
            "sources":[{"id":"synthetic-generator", "file":"tools/rebuild_statelens_demo.py",
                        "method":"deterministic fictional examples", "verified":False,
                        "locator":"generated values; not real experimental evidence"}], "studies":studies}
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "demo.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw = ASSETS / "sample-input"
    raw.mkdir(exist_ok=True)
    with (raw / "runs.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["state", "replicate", "latency", "latency_unit", "accuracy", "accuracy_unit"])
        for state in studies[0]["states"]:
            for row in state["observations"]:
                writer.writerow([state["id"],row["replicate"],row["values"]["latency"],
                                 row.get("units",{}).get("latency","ms"),row["values"]["accuracy"],"%"])
    (raw / "experiment-notes.md").write_text(
        "# Synthetic benchmark protocol\n\nThese are fictional demo values, not measured performance.\n"
        "States baseline/cache/quantized use CPU-A and fixed-v1 testset. Each unit-N is a matched independent workload batch.\n"
        "Compare latency (lower is better, practical margin 3 ms) and accuracy (higher is better, margin 0.5 percentage points).\n"
        "Only treatment is deliberately varied. Use baseline as reference.\n", encoding="utf-8")
    print(ASSETS / "demo.json")


if __name__ == "__main__":
    main()
