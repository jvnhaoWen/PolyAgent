# PolyAgent（重构版）

这是一个面向 OpenClaw 的 Polymarket Twitter 实时监控与自动下注 Skill。

## 目标

- 用 `poly-monitor new` 创建 7*24h 任务。
- 每个任务读取 `task.md` + `task_config.py` 初始化。
- 持续抓取对应 `tag_slug` 的 Polymarket 市场，过滤可交易市场。
- 构建 `all-MiniLM-L6-v2 + FAISS` 向量索引。
- 持续监听 `WATCH_USERS` 推特更新，做新闻-市场匹配。
- 调用 OpenClaw 生成最终交易决策，并在开启交易时自动下单。
- 支持任务常驻、查看、停止。

## 命令

```bash
# 1) 创建任务（交互式）
poly-monitor new

# 2) 后台启动任务（新进程，长期运行）
poly-monitor start --task iran_fast_reaction

# 3) 查看正在运行任务
poly-monitor list

# 4) 停止任务
poly-monitor stop --task iran_fast_reaction

# 5) 当前前台运行
poly-monitor run --task iran_fast_reaction
```

## 任务目录结构

```
tasks/<task_name>/
  task.md
  task_config.py
  data/
    events.jsonl
    extracted_markets.jsonl
    tweets.jsonl
    last_seen.json
  vector/
    events.faiss
    records.json
    meta.json
  logs/
    trades.jsonl
  test/
    decision_records.jsonl
```

## 必要环境变量

- `POLYMARKET_PRIVATE_KEY`（启用真实下单必须）
- `POLYMARKET_CHAIN_ID`、`POLYMARKET_FUNDER`（按需要）

> 推特 cookie 可直接放入 `task_config.py`：`TWITTER_AUTH_TOKEN`, `TWITTER_CT0`。

## 注意

- 系统不会保留“长期记忆”；每条新推文单独触发一次匹配和一次决策。
- 每次交易金额会被限制为不超过 `MAX_ASSET_USD`。
