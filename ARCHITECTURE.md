# ARCHITECTURE

## 1. Skill 入口与任务生命周期

- 入口命令：`poly-monitor`
- 子命令：
  - `new`：交互式创建任务（写入 `task.md` + `task_config.py`）
  - `start`：拉起独立后台进程（模拟“新 OpenClaw 进程”）
  - `list`：查看当前任务健康状态（pid/alive）
  - `stop`：停止选中任务
  - `run`：前台运行某任务（无限循环）

任务注册表：`.poly_monitor_registry.json`

## 2. 市场模块（Market）

`src/polyagent/market.py`

- 对 Gamma API 进行 offset 分页抓取（带重试、429 限流处理、重复页/空页停止条件）。
- 原始事件落盘：`events.jsonl`
- 过滤出可交易子市场：
  - `acceptingOrders == true`
  - `volume > 0`
  - 有有效 yes/no token
- 提取后落盘：`extracted_markets.jsonl`
- 若无匹配市场会输出：`There is no matched market for your key words currently.`

## 3. RAG 模块

`src/polyagent/rag.py`

- Embedding: `sentence-transformers/all-MiniLM-L6-v2`
- Index: `FAISS IndexFlatIP`
- 向量库构建输入：`extracted_markets.jsonl`
- 向量库产出：`vector/events.faiss`, `vector/records.json`, `vector/meta.json`
- 查询：每条推文触发一次 top-k 检索

## 4. 推特监控模块

`src/polyagent/runtime.py`

- 使用 `twikit.Client` + cookie (`TWITTER_AUTH_TOKEN`, `TWITTER_CT0`)
- 轮询 `get_latest_timeline`
- 仅处理 `WATCH_USERS` 用户
- 新推文落盘：`tweets.jsonl`

## 5. 决策与交易模块

- 匹配阈值：`RAG_SCORE_THRESHOLD`
- 匹配成功后组装 prompt（包含新闻、事件、token、MAX_ASSET_USD、媒体可信度）
- 调用 OpenClaw 命令（`OPENCLAW_COMMAND`）拿到 JSON 决策
- 解析交易动作后执行：
  - `buy/sell` 真实 CLOB 下单（`py-clob-client`）
- 每次触发都写调试记录：`test/decision_records.jsonl`
- 成功交易写审计日志：`logs/trades.jsonl`

## 6. 7*24h 持续运行与自动刷新

- `run_forever()` 永不退出。
- 双循环并发：
  - 市场刷新循环：每 `MARKET_REFRESH_INTERVAL_SECONDS` 重建市场+向量库
  - 推特监听循环：每 `TWITTER_POLL_INTERVAL_SECONDS` 拉取新推文并决策
