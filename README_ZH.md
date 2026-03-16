# POLY MONITOR（中文）

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE) [![arXiv](https://img.shields.io/badge/arXiv-Paper-b31b1b.svg)](#)

> “Facts do not cease to exist because they are ignored.” — Aldous Huxley

## 项目概览

这是一个 prompt-first 的 Polymarket 监控系统：

1. 交互式创建任务配置
2. 抓取 Gamma 市场并过滤可交易子市场
3. 用 MiniLM + FAISS 构建向量索引
4. 实时监控 Twitter/X 新闻
5. 达到 RAG 阈值后，使用默认决策模板 + 动态注入市场/新闻/config
6. 调用 `openclaw agent --message "<decision prompt>"`

## 安装与命令全局化

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
poly-monitor --help
```

## 推荐运行方式（tmux）

```bash
tmux new -s poly
poly-monitor run --task <task_name>    # 测试模式：终端打印全部输出
# 或
poly-monitor start --task <task_name>  # 实战模式：后台运行 + 日志优先
```

常用命令：

```bash
poly-monitor new
poly-monitor list
poly-monitor stop --task <task_name>
```

## 架构与运行模式

- `run`：用于测试，便于观察实时输出
- `start`：用于实战，输出写入任务日志
- 配置源：`tasks/<task_name>/task_config.py`
- 核心链路：market -> rag -> decision -> openclaw

## 日志说明

每个任务目录 `tasks/<task_name>/logs/` 下包含：

- `runtime_events.jsonl`：新闻与决策摘要
- `decision_prompts.jsonl`：触发阈值时的合成 prompt 与响应
- `trades.jsonl`：从响应中提取出的交易记录
- `monitor_status.log`：heartbeat 状态面板快照
- `start_stdout.log`：后台标准输出与错误输出

## TODO

- [ ] 交互界面版
- [ ] 扩展推特之外的自定义信息源
- [ ] 支持 `sell` / `split` / `merge` / `redeem`
- [ ] 支持策略、限价单等
