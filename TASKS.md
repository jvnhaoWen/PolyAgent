# PolyAgent Task Board

## Completed

- [x] 构建并发多 Agent 框架（独立循环，持续运行）。
- [x] 接入 Redis Streams 队列后端，并保留内存后端用于本地调试。
- [x] 移除限时运行参数，运行入口默认无限循环。
- [x] 实现 Gamma API 组合扫描。
- [x] 改进自然语言到查询参数解析（同义词、阈值抽取、时间窗口抽取）。
- [x] 接入真实 CLOB 下单主路径（buy/sell，基于 `py-clob-client`）。
- [x] 保留 split/merge 占位执行并记录审计日志。
- [x] 更新架构与运行文档。

## Next

- [ ] 接入链上 split/merge/redeem 真正执行。
- [ ] 引入更严格的订单前风险门控（敞口、相关性、回撤）。
- [ ] 增加 Redis consumer-group 的重试/死信队列策略。
- [ ] 增加端到端回测与沙盒账户模拟。
