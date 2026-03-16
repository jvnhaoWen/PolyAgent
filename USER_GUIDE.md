# Poly Monitor 用户指南

## 1. 安装与命令全局化

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
poly-monitor --help
```

建议在 `tmux` 中运行长期任务：

```bash
tmux new -s poly
poly-monitor run --task <task_name>
```

## 2. 创建任务

```bash
poly-monitor new
```

`new` 会写入：
- `tasks/<task_name>/task_config.py`

## 3. 启动任务

- `run`：测试模式，打印所有输出（便于调试）
- `start`：实战模式，输出重定向到日志

```bash
poly-monitor run --task <task_name>
poly-monitor start --task <task_name>
poly-monitor list
poly-monitor stop --task <task_name>
```

## 4. 实战日志（重点）

- `logs/runtime_events.jsonl`：新闻 + 决策摘要
- `logs/decision_prompts.jsonl`：达到阈值时的合成 prompt + 模型响应
- `logs/trades.jsonl`：交易动作记录（若响应中存在）
- `logs/monitor_status.log`：Heartbeat 状态面板

## 5. task_config.py 关键字段

- `WATCH_USERS`
- `TOPIC_TAG_SLUG`
- `RAG_SCORE_THRESHOLD`
- `MIN_TRADE_USDC` / `MAX_TRADE_USDC`
- `DECISION_ENABLED` / `TRADING_ENABLED`
- `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`
