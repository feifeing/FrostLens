# StateLens：开始使用

这是一个独立的实验比较 skill，适用于 Codex 和 Claude Code。需要 Python 3.11+，无需额外 Python 库。全部示例为合成数据。

在本文件所在的目录打开终端：

```bash
# 先运行示例，报告可离线打开
python scripts/statelens.py demo --out demo-report --open
# 安装到 Codex，或把 codex 换成 claude
python scripts/install.py --target codex
```

Windows 可用 `py -3` 代替 `python`。如果 skill 没有显示，重新打开助手会话。

向助手发送“使用 compare-experiments 比较我的实验文件夹，说明条件差异、指标变化和下一步需要补充的证据”。Codex CLI 可用 `$compare-experiments`，Claude Code 可用 `/compare-experiments`。

表格、结构化数据和文本可以由自带代码提取；图片、PDF、音视频或专用仪器格式依赖助手可用的读取工具。语义不明确时会标注待核对，不会凭空补值或假定独立重复。

安装器默认使用 Codex 的 `~/.agents/skills` 或 Claude Code 的 `~/.claude/skills`；自定义目录用 `--destination`。已有内容不会被静默覆盖，`--replace` 会先保留备份。

详细教程、计算限制和源码：[GitHub 项目](https://github.com/feifeing/FrostLens)。
