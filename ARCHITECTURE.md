# ARCHITECTURE

## 运行模式
- `poly-monitor run --task X`：测试模式（控制台输出完整状态）
- `poly-monitor start --task X`：实战模式（输出进入日志）

## 核心链路
1. `task_config.py` 读取配置
2. `market.py` 抓取并过滤市场
3. `rag.py` 建索引并检索
4. `decision.py` 用 `DEFAULT_DECISION_TEMPLATE` + 动态注入（市场/新闻/config）
5. 调用 `openclaw agent --message <decision prompt>`

## 运行时状态
`runtime.py` 在循环中维护状态并输出 heartbeat 面板：
- Markets
- Tweets
- Trades
- Latest News
- Recent Trades

## 日志
- `runtime_events.jsonl`：新闻与决策摘要
- `decision_prompts.jsonl`：触发阈值时合成 prompt 与响应
- `trades.jsonl`：从响应中提取出的交易记录
- `monitor_status.log`：状态面板快照
