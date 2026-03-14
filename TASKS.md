# TASKS

## 已完成

- [x] 改造成 prompt 驱动任务系统。
- [x] `new` 时先读取 task.md 并提问收集配置。
- [x] 所有运行参数统一从 task_config.py 读取。
- [x] 市场抓取 + 活跃事件过滤（acceptingOrders + volume 过滤）。
- [x] event 粒度 RAG（MiniLM + FAISS）。
- [x] 推特监控后实时匹配并按阈值触发。
- [x] decision.md 模板注入并调用 OpenClaw 做最终决策。
- [x] 接入真实 CLOB buy/sell 执行。
- [x] 测试期记录每次触发上下文到 test/。

## 待完成

- [ ] 对 Twitter 会话失效增加自动恢复与告警。
- [ ] 支持多新闻源融合（RSS/新华社等）。
- [ ] 扩展 split/merge/redeem 真实链上执行。
