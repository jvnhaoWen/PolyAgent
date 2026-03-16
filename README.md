# POLY MONITOR

```text
██████╗  ██████╗ ██╗      ██╗   ██╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗ 
██╔══██╗██╔═══██╗██║      ╚██╗ ██╔╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
██████╔╝██║   ██║██║       ╚████╔╝     ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
██╔═══╝ ██║   ██║██║        ╚██╔╝      ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
██║     ╚██████╔╝███████╗    ██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
╚═╝      ╚═════╝ ╚══════╝    ╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
```

> “Facts do not cease to exist because they are ignored.” — Aldous Huxley

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE) [![arXiv](https://img.shields.io/badge/arXiv-Paper-b31b1b.svg)](#)

[中文 README](./README_ZH.md) | [English README](./README_EN.md)

---

## What it does

Prompt-first Polymarket monitor for OpenClaw:

1. Create task config interactively.
2. Fetch Gamma events and filter active sub-markets.
3. Build MiniLM + FAISS index.
4. Watch Twitter/X accounts in real time.
5. When RAG score passes threshold, synthesize decision prompt using default template + dynamic market/news/config injection.
6. Call `openclaw agent --message "<decision prompt>"`.

## Install (global command in venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
poly-monitor --help
```

## Run (tmux recommended)

```bash
tmux new -s poly
poly-monitor run --task <task_name>    # test mode: prints output
# or
poly-monitor start --task <task_name>  # production mode: log-first
```

Other commands:

```bash
poly-monitor new
poly-monitor list
poly-monitor stop --task <task_name>
```

## Runtime behavior

- `run` = testing/debug, prints all status to terminal.
- `start` = production, runs in background and writes outputs/logs under task directory.

## Logs

Per task: `tasks/<task_name>/logs/`

- `runtime_events.jsonl` → incoming news + decision summaries
- `decision_prompts.jsonl` → synthesized prompt + model response (when threshold triggers)
- `trades.jsonl` → parsed trade actions (if response contains trade action)
- `monitor_status.log` → heartbeat dashboard snapshot
- `start_stdout.log` → background stdout/stderr capture

## TODO

- [ ] Interactive UI version
- [ ] Custom information sources beyond Twitter/X
- [ ] Support `sell`, `split`, `merge`, `redeem`
- [ ] Strategy and limit-order capabilities
