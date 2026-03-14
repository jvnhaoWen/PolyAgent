from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path('.poly_monitor_registry.json')
TASKS_ROOT = Path('tasks')

TASK_MD = """你是一个polymarket交易agent，你有在polymarket进行下单购买的能力，能根据提供的市场和新闻信息以及你自己的判断做出是否购买某一个事件特定头寸的决定。你现在需要询问用户task_config.py当中的信息来完成配置。"""

DECISION_MD = """你是 Polymarket 交易决策 Agent。

输入包含：
1) 新闻内容（tweet）
2) 匹配到的事件（event_title / event_description）
3) 可选子市场（child_options，含 yes/no token）
4) 风控参数（MAX_ASSET_USD）

你必须仅返回 JSON，不要返回其它文本：
{
  "should_trade": true/false,
  "side": "buy" | "sell",
  "token_id": "string",
  "amount_usd": number,
  "reason": "string"
}

约束：
- 若不确定，should_trade=false。
- amount_usd 不得超过 MAX_ASSET_USD。
"""

TASK_CONFIG_TEMPLATE = """TASK_NAME = {task_name!r}
MAX_ASSET_USD = {max_asset_usd}
TASK_INIT_TIME = {init_time!r}
MARKET_REFRESH_INTERVAL_SECONDS = 86400
TWITTER_POLL_INTERVAL_SECONDS = 60
WATCH_USERS = {watch_users!r}
TOPIC_TAG_SLUG = {tag_slug!r}
VOLUME_MIN = 1000000
RAG_SCORE_THRESHOLD = {rag_score_threshold}
DECISION_ENABLED = True
TRADING_ENABLED = True
OPENCLAW_COMMAND = ['openclaw', 'agent', '--message']
TRUSTED_MEDIA = ['Reuters', 'AP', 'BBCWorld', 'Bloomberg']
TWITTER_AUTH_TOKEN = ''
TWITTER_CT0 = ''
"""


@dataclass(slots=True)
class TaskMeta:
    task_name: str
    pid: int
    started_at: str


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def create_task_interactive() -> Path:
    print('\n--- task.md ---')
    print(TASK_MD)
    print('---------------\n')

    task_name = input('TASK_NAME: ').strip() or 'iran_fast_reaction'
    tag_slug = input('TOPIC_TAG_SLUG (e.g. iran): ').strip() or 'iran'
    watch_users_raw = input('WATCH_USERS (comma-separated, e.g. Reuters,AP,BBCWorld): ').strip() or 'Reuters,AP,BBCWorld'
    watch_users = [x.strip() for x in watch_users_raw.split(',') if x.strip()]
    max_asset_usd = float(input('MAX_ASSET_USD [10]: ').strip() or '10')
    rag_score_threshold = float(input('RAG_SCORE_THRESHOLD [0.70]: ').strip() or '0.70')

    task_dir = TASKS_ROOT / task_name
    (task_dir / 'data').mkdir(parents=True, exist_ok=True)
    (task_dir / 'vector').mkdir(parents=True, exist_ok=True)
    (task_dir / 'logs').mkdir(parents=True, exist_ok=True)
    (task_dir / 'test').mkdir(parents=True, exist_ok=True)

    (task_dir / 'task.md').write_text(TASK_MD, encoding='utf-8')
    (task_dir / 'decision.md').write_text(DECISION_MD, encoding='utf-8')

    (task_dir / 'task_config.py').write_text(
        TASK_CONFIG_TEMPLATE.format(
            task_name=task_name,
            max_asset_usd=max_asset_usd,
            init_time=datetime.now(timezone.utc).isoformat(),
            watch_users=watch_users,
            tag_slug=tag_slug,
            rag_score_threshold=rag_score_threshold,
        ),
        encoding='utf-8',
    )

    print(f'[OK] Created task: {task_dir}')
    print('请编辑 task_config.py 中 TWITTER_AUTH_TOKEN / TWITTER_CT0 后再运行。')
    return task_dir


def load_task_config(task_dir: Path) -> dict[str, Any]:
    cfg_path = task_dir / 'task_config.py'
    if not cfg_path.exists():
        raise FileNotFoundError(f'missing task_config.py: {cfg_path}')

    spec = importlib.util.spec_from_file_location(f'taskcfg_{task_dir.name}', cfg_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load {cfg_path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return {k: getattr(mod, k) for k in dir(mod) if k.isupper()}


def start_task_process(task_name: str) -> int:
    task_dir = TASKS_ROOT / task_name
    if not task_dir.exists():
        raise FileNotFoundError(f'task not found: {task_name}')

    cmd = [sys.executable, '-m', 'polyagent.cli', 'run', '--task', task_name]
    proc = subprocess.Popen(cmd, start_new_session=True)
    reg = _load_registry()
    reg[task_name] = asdict(TaskMeta(task_name=task_name, pid=proc.pid, started_at=datetime.now(timezone.utc).isoformat()))
    _save_registry(reg)
    return proc.pid


def list_tasks() -> list[dict[str, Any]]:
    reg = _load_registry()
    rows = []
    cleaned = {}
    for task_name, meta in reg.items():
        pid = int(meta['pid'])
        alive = _is_alive(pid)
        row = {**meta, 'alive': alive}
        rows.append(row)
        if alive:
            cleaned[task_name] = meta
    _save_registry(cleaned)
    return rows


def stop_task(task_name: str) -> bool:
    reg = _load_registry()
    meta = reg.get(task_name)
    if not meta:
        return False
    pid = int(meta['pid'])
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    reg.pop(task_name, None)
    _save_registry(reg)
    return True
