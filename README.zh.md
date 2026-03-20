<div align="center">

# Poly Monitor（中文）

<pre>
██████╗  ██████╗ ██╗  ██╗   ██╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗
██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
██████╔╝██║   ██║██║   ╚████╔╝     ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
██╔═══╝ ██║   ██║██║    ╚██╔╝      ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
██║     ╚██████╔╝███████╗██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
╚═╝      ╚═════╝ ╚══════╝╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
</pre>

> “Facts do not cease to exist because they are ignored.” — Aldous Huxley

[![PyPI](https://img.shields.io/badge/pypi-1.1.0-blue)](https://pypi.org/project/polyagent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-Poly%20Monitor-b31b1b.svg)]()

[English](./README.md) | [中文](./README.zh.md)

</div>

## 快速开始（建议在 tmux 里运行）

为了长时间稳定运行，建议把命令安装到当前环境后，在 `tmux` 会话里执行。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --no-cache-dir "git+https://github.com/pothitos/twikit.git@patch-1"
pip install -e .
poly-monitor new
poly-monitor run --task <task_name>   # 测试模式：前台打印完整输出
poly-monitor start --task <task_name> # 实战模式：后台 worker + 仪表板
```

> PyPI 上的 `twikit` 版本当前不可用，需先安装 GitHub `patch-1` 版本。

> 建议把 `poly-monitor run/start` 及相关操作都放在 tmux 里，避免会话中断。

## 架构与用户指南（合并版）

### 运行主流程
1. `poly-monitor new` 交互创建任务配置（`tasks/<task>/task_config.py`）。
2. 市场管线从 Gamma API 拉取并筛选活跃市场。
3. RAG 使用真实 `markets[].question` 构建向量；如果没有子 market，则用主 event 的 `title` 兜底。
4. Twitter 轮询关注账号。
5. 达到阈值后，合成决策 prompt 并调用 OpenClaw。
6. 交易返回与匹配新闻写入任务日志。

### CLI 模式
- `run`：测试模式，前台打印所有输出。
- `start`：实战模式，后台启动 worker，并在当前终端显示每分钟刷新一次的仪表板。

### Start 模式仪表板
`start` 模式终端只显示三个模块：
- 顶部状态栏：version、init time、当前 UTC 时间、呼吸灯、transactions / triggered news 数量。
- 中部资产模块：EOA / Proxy Wallet、Portfolio Value Summary、Recent Activity、Open Positions。
- 底部新闻模块：直接滚动展示 `tasks/<task>/data/tweets.jsonl` 中的最新新闻。

私钥读取顺序：
1. `POLY_PRIVATE_KEY`
2. `POLYMARKET_PRIVATE_KEY`
3. `PRIVATE_KEY`
4. `tasks/<task>/private_key.txt`
5. `.private_key`

### 核心调用
```bash
openclaw agent --message "<decision prompt>"
```

### 关键日志
- `tasks/<task>/logs/runtime_events.jsonl`：新闻、阈值触发记录、合成 prompt、交易返回。
- `tasks/<task>/logs/task_runtime.log`：后台 worker 运行日志。
- `tasks/<task>/test/decision_records.jsonl`：详细调试记录。

### 常用命令
```bash
poly-monitor list
poly-monitor stop --task <task_name>
```

## TODO
- [ ] 后续会更新交互界面版。
- [ ] 会扩展推特之外的自定义信息源。
- [ ] 支持 `sell`、`split`、`merge`、`redeem`。
- [ ] 支持策略、限价单等。

## License
MIT
