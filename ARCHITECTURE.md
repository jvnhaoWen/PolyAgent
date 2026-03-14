# ARCHITECTURE

## Prompt 驱动主流程

- `poly-monitor new`：
  - 展示 `task.md` 的角色与任务说明。
  - 询问用户 `TOPIC_TAG_SLUG`、`WATCH_USERS`、`MAX_ASSET_USD` 等关键信息。
  - 写入 `task_config.py`（其余参数保留默认）。
- `poly-monitor run/start`：
  - 读取 `task_config.py` 作为唯一配置源。
  - 自动执行数据抓取、过滤、向量构建、推特监控、决策、交易。

## 模块

### 1) tasking.py
- 创建任务目录与 `task.md` / `decision.md` / `task_config.py`
- 维护后台任务注册表与 start/list/stop

### 2) market.py
- 用 `TOPIC_TAG_SLUG` + `VOLUME_MIN` 调用 Gamma API
- 分页抓取与重试
- 过滤 `acceptingOrders=true` 且 `volume>0`
- 产物：`filtered_acceptingOrders.jsonl`（event + child_options）

### 3) rag.py
- 模型：`sentence-transformers/all-MiniLM-L6-v2`
- 索引：FAISS
- 在 event 粒度进行检索，返回匹配分数

### 4) runtime.py
- 读取 task 配置并长期运行：
  - 定时刷新市场与向量库
  - 实时轮询 twikit
- 每条新推文触发 RAG
- 分数 >= `RAG_SCORE_THRESHOLD` 时：
  - 将 tweet + event + child_options 注入 `decision.md` 模板
  - 调用 OpenClaw，解析 JSON 决策
  - 若 `TRADING_ENABLED`，执行真实交易

### 5) trading.py
- `py-clob-client` 封装
- 支持 market buy/sell
- 对金额做 `MAX_ASSET_USD` 上限约束

## 观测与调试
- 每次触发写入：`test/decision_records.jsonl`
- 成功下单写入：`logs/trades.jsonl`
