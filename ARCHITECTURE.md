# PolyAgent Architecture

## Overview
PolyAgent 是一个长期运行（24/7）的异步多 Agent 系统：每个 Agent 在独立循环中并发运行，通过消息队列通信。

## Queue Layer

- 默认使用 **Redis Streams**（`RedisMessageBus`）作为队列后端，支持跨进程/跨实例消费。
- 可切换为 `InMemoryMessageBus` 仅用于本地调试。
- 主题（topic）示例：`market_updates`、`news_signals`、`trade_signals`、`execution_requests`、`health`。

## Agent Topology

- **MarketAgent**
  - 轮询 Polymarket Gamma `/events`。
  - 支持高流动性、高成交量、临近结束等组合查询并投递 `market_updates`。

- **NewsAgent**
  - 轮询 RSS/新闻源。
  - 抽取关键词并映射为 tag，投递 `news_signals`。

- **StrategyAgent**
  - 消费 `news_signals` + `market_updates`。
  - 生成 `news_arbitrage` / `liquidity_breakout` 信号并投递 `trade_signals`。

- **ExecutionAgent**
  - 消费 `execution_requests` 与 `trade_signals`。
  - `buy/sell` 走真实 CLOB 提交流程；`split/merge` 先走模拟占位。
  - 所有执行结果写入 `logs/trades.log`。

- **RiskAgent**
  - 长期运行风控循环（当前为占位，可扩展仓位限制、回撤限制等）。

- **SchedulerAgent**
  - 持续采集 Agent 健康状态并发布到 `health` topic。

## CLOB Trading

`PolymarketClient` 使用 `py-clob-client`：

1. 通过环境变量加载私钥与链参数。
2. 构造并签名订单。
3. 提交到 CLOB（`post_order`）。
4. 失败时返回显式错误并保留可追溯日志。

## Security

- 私钥仅可来自环境变量，禁止硬编码。
- 日志中不记录私钥等敏感字段。
