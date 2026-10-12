# StateLens · 实验状态比较

**FrostLens 第二版：面向不同学科、可在 Codex 和 Claude Code 中使用的实验比较 skill。**

把实验文件或文件夹交给助手，它会识别数据、整理实验状态、检查比较条件，并输出可追溯的交互报告。适用于对照组与处理组、不同材料或工况、模型消融、同一样本处理前后等问题。

[English](README.en.md) · [下载 skill](https://github.com/feifeing/FrostLens/raw/refs/heads/main/downloads/compare-experiments-v0.2.0.zip) · [安装说明](docs/INSTALL.md) · [新手教程](docs/GETTING_STARTED.md) · [验证记录](docs/STATELENS_VALIDATION.md) · [第一版制冷工作台](FROSTLENS.md)

![StateLens 实验比较报告](docs/statelens.png)

## 可以解决哪些问题

| 需要回答的问题 | 提供的结果 |
|---|---|
| 文件格式混杂，从哪里开始？ | 文件清单、表格与文本提取、无法直接读取格式的后续处理任务 |
| 两个状态是否可以公平比较？ | 必要条件缺失、单位不兼容、非预期条件变化的提示 |
| 指标实际改变了多少？ | 原始均值、样本数、带单位的差值，以及适用时的重采样区间 |
| 差异是否有实际意义？ | 可调整的实际意义阈值，及结论随阈值变化的情况 |
| 多个指标各有改善，怎么取舍？ | 同一研究内的多指标权衡，不强行合成总分 |
| 结论来自哪里，如何复算？ | 数据指纹、来源位置、计算设置，以及 JSON/CSV/Markdown 输出 |

**不同学科共用比较流程，不共用一个“优劣总分”。** 材料强度、算法准确率与反应收率属于不同研究问题，应分别解释。

## 直接使用

下载并解压上面的 skill 压缩包，需要 **Python 3.11+**。在解压后的 `compare-experiments` 文件夹中打开终端：

```bash
# 安装到 Codex
python scripts/install.py --target codex
# 或安装到 Claude Code
python scripts/install.py --target claude
```

Windows 中如果命令名是 `py`，可把 `python` 改为 `py -3`。不需要 API 密钥或额外 Python 库。若 skill 未出现在助手中，重新打开会话。

然后给助手以下任务，把路径换成自己的文件夹：

```text
使用 compare-experiments 分析 ./my-experiment。
比较不同状态，说明哪些条件一致、哪些差异不能直接归因，
生成交互报告并保留数据来源。请用适合初学者的语言解释结果。
```

Codex CLI 可明确输入 `$compare-experiments`；Claude Code 可输入 `/compare-experiments`。具体目录、项目级安装与本机兼容方式见[安装说明](docs/INSTALL.md)。

## 先看一个无需助手的示例

```bash
python scripts/statelens.py demo --out demo-report --open
```

生成 `report.html`，双击也能打开。示例涵盖计算机科学、材料科学、化学控制和热流工程，**全部为合成数据**。可以切换研究和候选状态、查看条件差异、调整实际意义阈值、导出报告。

从完整仓库运行时，在脚本路径前加 `skills/compare-experiments/`。

## 文件接入的实际能力

| 输入 | 当前处理方式 |
|---|---|
| CSV、TSV、JSON、JSONL、TXT、MD、LOG | 自带代码直接提取，助手根据字段和实验记录整理含义 |
| XLSX | 自带代码读取工作表与缓存值；公式缺少缓存、日期等情况会提示核对 |
| 图片、PDF、扫描件、音视频 | 自动识别并交给宿主助手可用的视觉、文档或转录工具；提取结果保留来源与核对状态 |
| 时序、谱线、图像测量 | 按研究问题定义窗口、特征和独立实验单位；通用比较器接收经过核对的特征 |
| HDF5、MAT、仪器二进制等 | 识别为需要专用读取器的输入，保留任务；可由助手使用已有工具转换 |

这里的“自动”包括文件识别、读取路径选择和助手辅助整理，**不意味着一个脚本已能准确解码所有格式或理解所有实验**。工具缺失或实验含义不明时会说明具体缺口；不会编造测量值或把时间点数量当成独立重复次数。

自带脚本不联网；宿主模型处理数据时仍遵循其自身的数据与权限设置。生成的报告包含提供给它的数据和来源信息，分享前应检查内容。

## 有效比较的前提

- 明确对照状态、指标单位、独立实验单位，以及有意改变的因素。
- 配对实验按相同样本/批次 ID 对齐；配对不完整时不输出过强结论。
- 未知采样方式采用描述性比较。重复时间点、像素、技术重复不会自动等同于独立样本。
- 区间与阈值标签用于探索性判断，不等同于因果证明或经过多重比较校正的显著性检验。
- 只有明确规定的条件能被检查；软件不能排除未记录的混杂因素。

详细定义见 skill 内的[数据格式](skills/compare-experiments/references/schema.md)、[计算与解释](skills/compare-experiments/references/methods.md)和[混合输入指南](skills/compare-experiments/references/input-routes.md)。

## 开发与复算

```bash
# 仅验证通用 skill，无第三方 Python 依赖
python -m unittest discover -s tests -p "test_statelens_*.py" -v
python tools/rebuild_statelens_demo.py
python tools/package_statelens.py
```

第一版 FrostLens 的物理模型、数据格式和启动方式保持独立，见 [FROSTLENS.md](FROSTLENS.md)。通用 skill 无需安装 CoolProp。贡献新的学科案例时，请提供单位、实验单位、控制条件、原始来源和可验证的预期结果。

代码采用 MIT 许可。原创工作是文件接入、比较条件检查、来源记录和交互报告的组合实现；重采样与多目标比较采用已有方法，不宣称理论首创。
