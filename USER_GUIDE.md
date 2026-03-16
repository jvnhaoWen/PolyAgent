# Poly Monitor 用户指南

## 1. 安装与入口

```bash
pip install -e .
poly-monitor --help
```

## 2. 创建任务（交互询问每个配置项）

```bash
poly-monitor new
```

`new` 会写入：
- `tasks/<task_name>/decision.md`
- `tasks/<task_name>/task_config.py`

如果你在输入时直接回车，将使用默认值，例如：
- `WATCH_USERS = ["Reuters", "cnnbrk", "EnglishFars", "IranIntl_En", "BBCBreaking"]`
- `MIN_TRADE_USDC = 5`
- `MAX_TRADE_USDC = 10`

## 3. 启动任务

前台运行（方便调试）：
```bash
poly-monitor run --task <task_name>
```

后台运行（7*24h）：
```bash
poly-monitor start --task <task_name>
```

查看运行中任务：
```bash
poly-monitor list
```

停止任务：
```bash
poly-monitor stop --task <task_name>
```

## 4. task_config.py 字段说明（全部来自交互初始化）

- `TASK_NAME`: 任务名
- `MAX_ASSET_USD`: 单次决策可参考的最大资金上限
- `MIN_TRADE_USDC` / `MAX_TRADE_USDC`: 决策 prompt 中的交易区间
- `TASK_INIT_TIME`: 初始化时间
- `MARKET_REFRESH_INTERVAL_SECONDS`: 市场与向量库刷新周期
- `TWITTER_POLL_INTERVAL_SECONDS`: 推特轮询周期
- `WATCH_USERS`: 监控账号列表
- `TOPIC_TAG_SLUG`: Gamma API 检索关键词
- `VOLUME_MIN`: 市场筛选最小交易量
- `RAG_SCORE_THRESHOLD`: 触发决策阈值
- `DECISION_ENABLED`: 是否调用 OpenClaw
- `TRADING_ENABLED`: 是否允许在 prompt 中执行下单动作
- `OPENCLAW_COMMAND`: 默认为 `['openclaw','agent','--message']`
- `TRUSTED_MEDIA`: 提示词上下文用
- `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`: twikit 登录 cookie

## 5. 系统核心调用

真正与 OpenClaw 交互只有一步：

```bash
openclaw agent --message "<decision prompt>"
```

## 6. 运行日志

- `data/tweets.jsonl`: 抓到的推文
- `logs/runtime_events.jsonl`: 新闻与决策摘要日志（新增）
- `test/decision_records.jsonl`: 每次触发的完整调试记录
