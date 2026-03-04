# PolyAgent

基于 asyncio + Redis Streams 的 Polymarket 多 Agent 交易系统。

## 运行（默认无限循环）

```bash
PYTHONPATH=src python -m polyagent.app
```

> 不再提供 `--run-seconds`，进程默认长期运行（24/7）。

## 关键环境变量

- `MESSAGE_BUS_BACKEND=redis`（默认）或 `memory`
- `REDIS_URL=redis://localhost:6379/0`
- `REDIS_STREAM_PREFIX=polyagent`
- `POLY_GAMMA_BASE_URL`
- `POLY_CLOB_BASE_URL`
- `POLYMARKET_PRIVATE_KEY`（实盘必需）
- `POLYMARKET_CHAIN_ID`（默认 `137`）
- `POLYMARKET_FUNDER`
- `POLYMARKET_SIGNATURE_TYPE`
- `TRADE_LOG_PATH`

## 交易说明

- `buy/sell`：通过 `py-clob-client` 提交真实 CLOB 订单。
- `split/merge`：当前记录为模拟动作（需后续接入链上仓位操作接口）。

## 日志

交易记录写入 `logs/trades.log`。
