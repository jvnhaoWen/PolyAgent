# TASKS

## 已完成
- [x] 决策逻辑在 `decision.py` 中集中管理（使用默认模板 + 动态注入）
- [x] OpenClaw 交互统一为 `openclaw agent --message <decision prompt>`
- [x] `task_config.py` 成为唯一配置源
- [x] `new` 阶段对 task_config 每一项进行交互初始化（支持回车默认）
- [x] 默认 WATCH_USERS 为 `Reuters,cnnbrk,EnglishFars,IranIntl_En,BBCBreaking`
- [x] 新增 MIN/MAX 交易金额配置注入决策 prompt
- [x] 删除所有“仅兼容说明、未参与主流程”的旧模块
- [x] runtime 在收到新闻时打印并写日志，决策结果也写日志

## 待完成
- [ ] twitter cookie 过期自动提示与刷新流程
- [ ] 多源新闻并行输入
