```text
██████╗  ██████╗ ██╗  ██╗   ██╗
██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝
██████╔╝██║   ██║██║   ╚████╔╝ 
██╔═══╝ ██║   ██║██║    ╚██╔╝  
██║     ╚██████╔╝███████╗██║   
╚═╝      ╚═════╝ ╚══════╝╚═╝   
```

# POLY MONITOR

Prompt-first Polymarket monitor for OpenClaw.

- 中文文档：见 `README_ZH.md`
- English docs: see `README_EN.md`

## Quick Start (global command + tmux recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

After installation, `poly-monitor` is available as a global command in your active shell/venv.

Recommended to run long-running tasks in **tmux**:

```bash
tmux new -s poly
poly-monitor run --task <task_name>   # test mode (prints full output)
# or
poly-monitor start --task <task_name> # production mode (write logs)
```

Other commands:

```bash
poly-monitor new
poly-monitor list
poly-monitor stop --task <task_name>
```

## Runtime Logging

Per task (`tasks/<task_name>/logs/`):
- `runtime_events.jsonl` → news + decision summaries
- `decision_prompts.jsonl` → synthesized prompt + response when threshold triggers
- `trades.jsonl` → extracted trade actions from model response (if any)
- `monitor_status.log` → heartbeat dashboard snapshot

## TODO

- [ ] 交互界面版（GUI/TUI）
- [ ] 推特之外的自定义信息源扩展
- [ ] 支持 sell / split / merge / redeem
- [ ] 支持策略、限价单等高级能力
