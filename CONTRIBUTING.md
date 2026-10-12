# Contributing

谢谢你帮助 StateLens / FrostLens 改善科研比较和可复算性。

第二版通用 skill 位于 `skills/compare-experiments/`，只需 Python 3.11+ 标准库。运行 `python -S -m unittest discover -s tests -p "test_statelens_*.py" -v` 和演示命令即可开始，无需安装第一版的科学计算依赖。第一版的开发步骤保留如下。

## 开始

1. 创建虚拟环境并执行 `python -m pip install -e .`。
2. 运行 `python -m unittest discover -s tests -v`。
3. 启动 `python -m frostlens serve`，复现一个内置案例。
4. 将问题描述、相关版本、可公开的最小样例和预期行为放入 issue 或 pull request。

## 适合首次贡献

- 给输入错误添加更清楚的解释和对应测试。
- 增加英文界面或改善键盘/屏幕阅读器操作。
- 提供能复现的“拟合好但外推错”合成案例，明确真实生成机制。
- 用独立实现核对一个循环工况；注明 CoolProp 版本、状态、单位和容差。

## 科学变更要求

涉及模型或算法的变更，请说明公式、单位、假设、数据来源、适用域与失效情形。不能把合成恢复当作实验验证，也不能仅以拟合误差下降论证可辨识性。测试应检验物理不变量或外部可预期结果，而不只重复实现。

公开实测数据前，请确认你有分享权限并移除个人、设备或机构敏感信息。用户数据不应被写入默认案例；不要把局部电脑路径或密钥加入仓库。

## 架构

- `skills/compare-experiments/scripts/intake.py`：混合文件接入与原始来源记录。
- `skills/compare-experiments/scripts/engine.py`：单位、条件、抽样设计与比较结果。
- `skills/compare-experiments/scripts/report.py` / `assets/report.html`：离线交互报告。
- `skills/compare-experiments/SKILL.md` / `references/`：助手流程、输入路由与方法边界。

新学科案例应说明独立实验单位、控制条件、单位和预期行为；不要把任意记录数当作样本数。比较条件不足时保留描述性输出，不应通过放松检查来得到“胜出”结论。

- `frostlens/model.py` / `core.py`：物性、前向计算、拟合、实验设计。
- `frostlens/io.py`：CSV 契约、规范 JSON 与数据指纹。
- `frostlens/server.py`：仅本机的 HTTP 接口与来源标记。
- `frostlens/web/`：无构建步骤的界面。
- `examples/`：明确标注的合成案例。
- `tests/`：物理、算法、数据交换与服务边界检查。

尽量保持启动简单。新依赖需说明必要性和许可。提交贡献即表示你同意以仓库 MIT 许可分发该贡献。
