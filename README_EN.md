# POLY MONITOR (English)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE) [![arXiv](https://img.shields.io/badge/arXiv-Paper-b31b1b.svg)](#)

> “Facts do not cease to exist because they are ignored.” — Aldous Huxley

## Overview

Prompt-first Polymarket monitoring pipeline:

1. Interactive task configuration
2. Gamma market scraping + active sub-market filtering
3. MiniLM + FAISS indexing
4. Real-time Twitter/X monitoring
5. Threshold trigger -> default decision template + dynamic market/news/config injection
6. `openclaw agent --message "<decision prompt>"`

## Install (global command in your venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
poly-monitor --help
```

## Recommended operation (tmux)

```bash
tmux new -s poly
poly-monitor run --task <task_name>    # testing mode: print all outputs
# or
poly-monitor start --task <task_name>  # production mode: background + logs
```

Common commands:

```bash
poly-monitor new
poly-monitor list
poly-monitor stop --task <task_name>
```

## Runtime modes & architecture

- `run`: test/debug mode with full console output
- `start`: production mode with log-first output
- Single configuration source: `tasks/<task_name>/task_config.py`
- Core flow: market -> rag -> decision -> openclaw

## Logs

Per task: `tasks/<task_name>/logs/`

- `runtime_events.jsonl` (news + decision summaries)
- `decision_prompts.jsonl` (synthesized prompts + responses)
- `trades.jsonl` (parsed trade actions)
- `monitor_status.log` (heartbeat dashboard snapshots)
- `start_stdout.log` (background stdout/stderr)

## TODO

- [ ] Interactive UI version
- [ ] Extend custom sources beyond Twitter/X
- [ ] Support `sell` / `split` / `merge` / `redeem`
- [ ] Add strategy and limit-order capabilities
