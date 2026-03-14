# TASKS

## 已完成

- [x] 完全重构为 `poly-monitor` 任务制系统。
- [x] `poly-monitor new` 支持交互式初始化任务（tag_slug、MAX_ASSET_USD、WATCH_USERS 等）。
- [x] 增加后台进程管理：`start/list/stop`。
- [x] 市场抓取模块（分页+重试+限流处理+停止条件）。
- [x] 活跃市场过滤与 token 提取（过滤 acceptingOrders=false 和 volume=0）。
- [x] RAG 索引构建（MiniLM + FAISS）和新闻检索。
- [x] 推特实时监控（twikit）并与市场匹配。
- [x] OpenClaw 决策调用与交易执行链路。
- [x] 每次触发写 `test/decision_records.jsonl` 便于测试期观察。
- [x] 交易日志写 `logs/trades.jsonl`。

## 下一步

- [ ] 增加多源新闻（RSS、新华社）融合与权重策略。
- [ ] 增加更细化的仓位和风控规则（单日上限、连续亏损熔断）。
- [ ] 增加真实 `split/merge/redeem` 执行模块。
- [ ] 增加 e2e 回放测试数据集。
