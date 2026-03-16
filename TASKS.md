# TASKS

## 已完成
- [x] 将决策逻辑迁移到 `decision.py`
- [x] 将 OpenClaw 交互统一为 `openclaw agent --message <decision prompt>`
- [x] 让 `task_config.py` 成为唯一配置源
- [x] `new` 阶段对 task_config 每一项进行交互初始化（支持回车默认）
- [x] 默认 WATCH_USERS 调整为 `Reuters,cnnbrk,EnglishFars,IranIntl_En,BBCBreaking`
- [x] 增加 MIN/MAX 交易金额配置注入决策 prompt
- [x] runtime 去除对 trading 模块耦合
- [x] 新增 `USER_GUIDE.md`

## 待完成
- [ ] 增加 twitter cookie 过期自动提示与刷新流程
- [ ] 增加多源新闻并行输入
