# 安装 StateLens skill

需要 Python 3.11+ 和支持本地 skill 的 Codex 或 Claude Code。自带比较、提取和报告代码只使用 Python 标准库；没有独立服务、API 密钥或云端账户要求。宿主助手本身的使用要求不变。

## 下载后安装

下载 [compare-experiments-v0.2.0.zip](https://github.com/feifeing/FrostLens/raw/refs/heads/main/downloads/compare-experiments-v0.2.0.zip)，解压后进入 `compare-experiments` 文件夹。

```bash
python scripts/install.py --target codex
python scripts/install.py --target claude
# 如果两者都需要：
python scripts/install.py --target both
```

Windows 如果安装了 Python Launcher，可用 `py -3` 代替 `python`。先运行 `python --version` 确认版本。

安装器把完整 skill 复制到所选目录，不改动宿主配置，也不联网。重复安装相同内容不会覆盖文件。更新已有内容时，使用 `--replace`；旧版本会保存在 skill 搜索目录之外的 `statelens-backups` 中。

| 目标 | 用户级目录 | 项目级目录 |
|---|---|---|
| Codex | `~/.agents/skills/compare-experiments` | `<project>/.agents/skills/compare-experiments` |
| Claude Code | `~/.claude/skills/compare-experiments` | `<project>/.claude/skills/compare-experiments` |

Codex 的本地发现目录和 `$skill-name` 调用方式依据 [OpenAI 官方文档](https://learn.chatgpt.com/docs/build-skills)；Claude Code 的目录和 `/skill-name` 调用方式依据 [Claude Code 官方文档](https://code.claude.com/docs/en/skills)。文档核对日期：2026-10-11。

项目级安装示例：

```bash
python scripts/install.py --target both --scope project --project /path/to/project
```

若当前 Codex 环境明确使用旧的 `~/.codex/skills` 或自定义 `$CODEX_HOME/skills`，可指定它实际读取的父目录：

```bash
python scripts/install.py --target codex --destination /path/to/codex-home/skills
```

不要同时安装到多个会被同一宿主扫描的位置，以免重复显示。

## 使用方式

Codex CLI / IDE 中输入 `$compare-experiments`；Claude Code 中输入 `/compare-experiments`。也可以直接说“使用 compare-experiments 比较这个实验文件夹”。不同客户端的菜单可能不同；如果没有出现，重新打开会话并确认 `SKILL.md` 位于上述 skill 文件夹内，而不是多套了一层压缩包目录。

Claude Code 的本机用户级安装不会自动同步到云端会话；需要云端使用时，采用项目级安装并提交到相应项目，或使用该宿主提供的 skill 分发方式。

## 不安装到助手也能运行

```bash
python scripts/statelens.py demo --out demo-report --open
python scripts/statelens.py intake ./my-experiment --out ./work/intake
python scripts/statelens.py compare dataset.json --out ./work/report
```

`intake` 提取文件与记录待办，语义映射由助手完成；`compare` 接收已经整理好的[比较数据格式](../skills/compare-experiments/references/schema.md)。两者不能互相替代。

## 卸载与更新

删除自己安装的 `compare-experiments` 文件夹即可卸载；安装器未修改其他配置。更新时从可信来源下载新包，并保留原有实验数据。报告与输入文件默认在你指定的工作目录，不在 skill 安装目录中。
