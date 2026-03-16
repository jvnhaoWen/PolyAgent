# ARCHITECTURE

## 目标
将系统变为 prompt-first：
- task 负责参数与上下文（task_config.py）
- decision.py 负责构建最终 prompt 并调用 OpenClaw
- 本项目不直接耦合交易执行模块

## 模块

### tasking.py
- `new`：逐项询问配置，写入 task_config.py
- `start/list/stop`：任务进程管理

### market.py
- 基于 `TOPIC_TAG_SLUG` + `VOLUME_MIN` 抓 Gamma API
- 过滤 `acceptingOrders=true` 且 `volume>0`
- 输出 `filtered_acceptingOrders.jsonl`

### rag.py
- 模型：`all-MiniLM-L6-v2`
- 索引：FAISS
- 对推文做 event 粒度召回

### decision.py
- 构建动态 prompt（市场详情 + 新闻 + 风控）
- 核心调用：`openclaw agent --message "<decision prompt>"`

### runtime.py
- 读取 task_config.py（唯一配置源）
- 周期刷新市场与向量
- 推特实时轮询
- 收到新闻时打印并写入 `logs/runtime_events.jsonl`
- 决策结果（是否触发、命中事件、回复摘要）写入 `logs/runtime_events.jsonl`
- 完整触发上下文写入 `test/decision_records.jsonl`

## 配置更新
- 任务 stop 后再 start/run 会重新读取 task_config.py
- runtime 运行中也会在轮询中重新加载 config，确保 prompt 使用最新配置
