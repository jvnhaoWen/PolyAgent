# PolyAgent Prompt-Driven Monitor

这是一个 **prompt 驱动** 的 Polymarket 监控项目。

## 核心流程

1. `poly-monitor new` 交互创建任务并写入 `task_config.py`
2. 用配置抓取市场（Gamma API）并过滤活跃市场
3. 构建 MiniLM + FAISS 向量库
4. 监控推特账号新消息
5. RAG 分数达到阈值后，使用 DEFAULT_DECISION_TEMPLATE 动态注入市场/新闻/config
6. 调用：`openclaw agent --message "<decision prompt>"`

> 与 OpenClaw 的真实交互只有上面这一步。

## 快速开始

```bash
poly-monitor new
poly-monitor run --task <task_name>
```

详见 `USER_GUIDE.md`。
