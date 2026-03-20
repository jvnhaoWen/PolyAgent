<div align="center">

# Poly Monitor

<pre>
██████╗  ██████╗ ██╗  ██╗   ██╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗
██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
██████╔╝██║   ██║██║   ╚████╔╝     ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
██╔═══╝ ██║   ██║██║    ╚██╔╝      ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
██║     ╚██████╔╝███████╗██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
╚═╝      ╚═════╝ ╚══════╝╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
</pre>

> “Facts do not cease to exist because they are ignored.” — Aldous Huxley

[![PyPI](https://img.shields.io/badge/pypi-1.1.0-blue)](https://pypi.org/project/polyagent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-Poly%20Monitor-b31b1b.svg)]()

[English](./README.md) | [中文](./README.zh.md)

</div>

## Quick Start (recommend in tmux)

For long-running monitoring, use a **global command in your shell session** and run inside `tmux`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --no-cache-dir "git+https://github.com/pothitos/twikit.git@patch-1"
pip install -e .
poly-monitor new
poly-monitor run --task <task_name>   # test mode: print all outputs
poly-monitor start --task <task_name> # production mode: background worker + terminal dashboard
```

> `twikit` from PyPI is no longer reliable here; install the `patch-1` GitHub build first.

> Recommended: run `poly-monitor start --task xxx` and other operations in tmux so the session can stay alive.

## Unified Architecture + User Guide

### Runtime flow
1. `poly-monitor new` creates task config (`tasks/<task>/task_config.py`).
2. Market pipeline fetches from Gamma API and filters active markets.
3. RAG builds vectors from real market questions; if no child market exists, it falls back to the event title.
4. Twitter watcher polls watched users.
5. If score reaches threshold, decision prompt is synthesized and sent to OpenClaw.
6. Trade response and matched news are persisted into task logs.

### CLI modes
- `run`: testing mode, keeps printing outputs in foreground.
- `start`: production mode, starts the worker in background and shows a terminal dashboard refreshed every minute.

### Start-mode dashboard
The `start` dashboard shows exactly three terminal blocks:
- top status banner: version, init time, current UTC time, heartbeat, transactions / triggered news counts.
- portfolio block: EOA / proxy wallet, portfolio value summary, recent activity, open positions.
- rolling news block: latest entries from `tasks/<task>/data/tweets.jsonl`.

Private key lookup order for the dashboard: `POLYMARKET_PRIVATE_KEY`

### Core command
```bash
openclaw agent --message "<decision prompt>"
```

### Key logs
- `tasks/<task>/logs/runtime_events.jsonl`: news, threshold-trigger records, synthesized prompts, and trade responses.
- `tasks/<task>/logs/task_runtime.log`: background worker log stream.
- `tasks/<task>/test/decision_records.jsonl`: detailed trigger debug records.

### Common task operations
```bash
poly-monitor list
poly-monitor stop --task <task_name>
```

## TODO
- [ ] Interactive UI version will be added.
- [ ] Extend to custom information sources beyond Twitter.
- [ ] Support `sell`, `split`, `merge`, `redeem`.
- [ ] Support strategies and limit orders.

## License
MIT
