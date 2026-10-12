# StateLens 0.2.0 验证记录

验证日期：2026-10-12。示例均为合成数据，不构成任何学科的实测结论。

## 本地验证

- Windows、Python 3.12：完整回归测试 101 项，100 项通过，1 项因 Windows 无符号链接创建权限跳过；实际目录联接保护测试通过。
- 独立报告浏览器检查 43 项全部通过：四学科切换、指标筛选、阈值边界、原始结果与情景分离、导出、390 像素布局、恶意内容转义、无外部网络请求。
- skill 元数据通过 skill-creator 的验证脚本。验证器使用 PyYAML；发布的 skill 本身没有此依赖。
- ZIP 内 16 个源文件逐项校验 SHA-256；在临时目录解压后，使用 Python 的 `-S` 模式运行示例，确认不依赖第三方包。
- 从解压包安装到 Codex 与 Claude Code 的项目目录，两份安装后的脚本均成功生成四学科报告。此项验证包结构、安装目录和运行脚本，不等于已在两个产品客户端完成真实会话测试。
- 混合输入试用：从合成 CSV 和实验说明整理出 24 条观测、48 个指标值；独立核对来源文件指纹、数值和单位，98 项核对全部通过。两种候选状态的配对均为 8 对。

## 自动验证

[GitHub Actions](https://github.com/feifeing/FrostLens/actions) 在每次提交后执行 Windows/Linux、Python 3.11/3.13 回归测试，以及第一版工作台与 StateLens 浏览器测试。请以相应提交的运行结果为准。

复现：

```bash
python -m unittest discover -s tests -v
python -S skills/compare-experiments/scripts/statelens.py demo --out local-reports/statelens
node tests/statelens-browser.mjs
python tools/package_statelens.py
```

完整回归测试需要第一版的依赖；仅运行 `test_statelens_*.py` 和 skill 脚本无需第三方 Python 包。浏览器测试需要 Playwright 和 Chromium。

## 解释边界

测试验证软件行为，不证明实验设计或科学结论正确。必要条件未声明时只作描述；已记录条件通过检查，也不能排除未记录混杂因素。区间用于探索，没有多重比较校正。PDF、图片和专有仪器格式依赖宿主实际可用的工具，未读取的文件不会被算作分析完成。

下载包校验值见 [SHA256SUMS.txt](../downloads/SHA256SUMS.txt)。
