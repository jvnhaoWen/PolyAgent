# AGENTS.md — OpenClaw Polymarket Trading Skill

## 1 项目目标

本项目实现一个 **OpenClaw Skill**：

Polymarket Autonomous Trading Skill

该 Skill 允许 OpenClaw Agent：

* 查询 Polymarket 市场
* 分析市场
* 监听新闻
* 自动生成交易策略
* 自动执行交易
* 用户手动触发交易

系统必须 **长期运行（24/7）**。

Agent 必须持续循环运行。

Agents must run concurrently.
Each agent runs in its own loop.
Communication uses message queues.

该md文件中的思路可以根据需要更改，接口设计可以灵活改变。
你需要创建并根据任务更新ARCHITECTURE.md TASKS.md。
你可以访问https://docs.polymarket.com/以及下面的子页面参考api以及交易行为的设计。
你可以访问clawhub.ai寻找现成的新闻搜索openclaw skill把他们用于该sikll的新闻、社交媒体查询。
交易以及新闻社媒搜索需要优化、加速给用户最好的使用体验。

---

# 2 Polymarket API 规范

Agent 必须参考官方文档：

https://docs.polymarket.com/

尤其包括：

* Gamma API
* CLOB API
* Orders
* Markets
* Positions
* Split / Merge

Agent 必须可以动态解析 API 结构，而不是只写死查询。
可以包含常见的API结构如：
```
https://gamma-api.polymarket.com/events?limit=10&active=True&tag_slug=china
使用场景：想要根据推特、新华社以及其他权威新闻进行监听，一旦出现较大新闻、政治类事件通过tag_lug关键词快速筛选相关事件快速反应形成相关事件信息差、对冲的事件组合。（适合：秒到分钟级反应下单）
# 1.2常见可用于筛选的字段
1）active=true&closed=false 2）volume_min=500000至少成交总量 以及liquidity
3）还没想好order=commentCount&ascending=false怎么用 4）总成交量大却start_date_min=最近时间才出来的market需要留意（突发爆火事件）
5）end_date_max=2026-03-04T15:00:00Z指定最近快要结束的事件
```

---

# 3 Agent 架构

系统包含以下 Agent：

Market Agent （Polymarket市场信息）
News Agent （社交媒体或新闻信息）
Strategy Agent （第一个版本可以暂时不设计）
Execution Agent （执行连接私钥 cp .env等操作以及针对确定好的市场头寸的buy sell split merge redeem操作）
Risk Agent （风控第一个版本可以暂时不设计）
Scheduler Agent 

所有 Agent 必须 **并发运行**。

系统运行模型：

async event loop

通信方式：

message queue

推荐：

Redis queue / asyncio queue

---

# 4 Market Agent

职责：

扫描 Polymarket 市场。

数据来源：

Gamma API等，具体参考https://docs.polymarket.com/api-reference下面的子目录doc。

Agent 必须能够组合查询参数。

支持字段：

active
closed
tag_slug
volume
liquidity
start_date
end_date
order
ascending

Agent 应该提供以下组合查询方法：

可选高流动性市场：

liquidity > 100000（默认，可以自定义）

高成交量市场：

volume > 1000000（默认，可以自定义）

新创建热门市场：

start_date_min = recent
volume spike

即将结束市场：

end_date_max = near

实时更新市场：

order = updatedAt
ascending = false

---

# 5 Natural Language → API 查询

Agent 必须支持：

用户自然语言 → API 参数映射

例如：

用户输入：

"查找中国相关高流动性市场"

解析为：

tag_slug=china
liquidity > 100000

用户输入：

"最近爆火市场"

解析为：

order=updatedAt
volume spike

Agent 应自动构造 Gamma API 请求。

---

# 6 News Agent

职责：

监听新闻并触发市场查询。

数据源：

Twitter / X
RSS
新华社
金融媒体

流程：

news → keyword → tag_slug → search market

关键词示例：

china
election
war
bitcoin
fed

---

# 7 Strategy Agent

职责：

生成交易信号。

可使用：

价格变化
成交量变化
流动性变化
Kyle lambda

Kyle lambda：

price impact = price change / volume

策略示例：

news arbitrage
momentum strategy
liquidity breakout

---

# 8 Execution Agent

负责执行交易。

必须支持：

自动交易
用户手动交易

接口

订单执行使用：

Polymarket CLOB API等，具体参考https://docs.polymarket.com/api-reference的各级子文件提供的接口。

---

# 9 Split / Merge

Execution Agent 必须支持：

split position
merge position

用于：

套利
组合市场

---

# 10 用户交易接口

系统必须提供：

用户手动交易接口。

例如：
可以通过自然语言转化为函数执行。
buy(token_id, price, size)

sell(token_id, price, size)

merge(position)

split(position)

---

# 11 自动交易接口

Strategy Agent 可以触发：

auto_trade(signal)

Execution Agent 必须记录：

交易时间
市场
价格
数量
策略

所有交易必须可追溯。

---

# 12 日志系统

日志必须记录：

market scan
news trigger
signals
orders

日志路径：

logs/trades.log

---

# 13 安全

私钥必须来自：

environment variables

禁止写入代码。

禁止记录到日志。

---

# 14 Scheduler Agent

Scheduler Agent 负责：

启动 agents
监控 agent 健康
自动重启 agent

系统必须持续运行。
