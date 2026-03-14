# PolyAgent（Prompt 驱动版）

这是一个 **prompt 驱动** 的 OpenClaw Skill：每次 `new` 一个任务后，先读取 `task.md`，再引导用户补齐 `task_config.py`，随后按配置自动执行：

1. 市场抓取（Gamma API，`tag_slug` 来自用户配置）
2. 活跃市场过滤（`acceptingOrders=true` 且 `volume>0`）
3. 向量索引构建（MiniLM + FAISS）
4. 推特实时监控（twikit）
5. 新闻检索触发后注入 `decision.md` 模板
6. 调用 OpenClaw 输出 JSON 决策
7. 结合私钥签名能力执行下单

## 命令

```bash
poly-monitor new
poly-monitor run --task <task_name>
poly-monitor start --task <task_name>
poly-monitor list
poly-monitor stop --task <task_name>
```

## 配置来源（唯一）

每个任务的所有运行参数都来自 `tasks/<task_name>/task_config.py`。

关键字段：
- `TASK_NAME`
- `MAX_ASSET_USD`
- `TASK_INIT_TIME`
- `MARKET_REFRESH_INTERVAL_SECONDS`
- `WATCH_USERS`
- `TOPIC_TAG_SLUG`
- `VOLUME_MIN`
- `RAG_SCORE_THRESHOLD`
- `DECISION_ENABLED`
- `TRADING_ENABLED`

## 任务目录

```
tasks/<task_name>/
  task.md
  decision.md
  task_config.py
  data/events.jsonl
  data/filtered_acceptingOrders.jsonl
  data/tweets.jsonl
  vector/events.faiss
  vector/events.json
  test/decision_records.jsonl
  logs/trades.jsonl
```

## 必填

- `task_config.py` 中 `TWITTER_AUTH_TOKEN`, `TWITTER_CT0`
- 环境变量 `POLYMARKET_PRIVATE_KEY`（真实交易）
