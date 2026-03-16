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

TASK_CONFIG_TEMPLATE = """TASK_NAME = {task_name!r}
MAX_ASSET_USD = {max_asset_usd}
MIN_TRADE_USDC = {min_trade_usdc}
MAX_TRADE_USDC = {max_trade_usdc}
TASK_INIT_TIME = {init_time!r}
MARKET_REFRESH_INTERVAL_SECONDS = {market_refresh_interval}
TWITTER_POLL_INTERVAL_SECONDS = {twitter_poll_interval}
WATCH_USERS = {watch_users!r}
TOPIC_TAG_SLUG = {tag_slug!r}
VOLUME_MIN = {volume_min}
RAG_SCORE_THRESHOLD = {rag_score_threshold}
DECISION_ENABLED = {decision_enabled}
TRADING_ENABLED = {trading_enabled}
OPENCLAW_COMMAND = {openclaw_command!r}
TRUSTED_MEDIA = {trusted_media!r}
TWITTER_AUTH_TOKEN = {twitter_auth_token!r}
TWITTER_CT0 = {twitter_ct0!r}
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


def _input_default(prompt: str, default: str) -> str:
    value = input(f'{prompt} [{default}]: ').strip()
    return value if value else default


def _input_bool(prompt: str, default: bool) -> bool:
    raw = _input_default(prompt, 'true' if default else 'false').lower()
    return raw in {'true', '1', 'yes', 'y'}


def create_task_interactive() -> Path:
    task_name = _input_default('TASK_NAME', 'iran_fast_reaction')
    tag_slug = _input_default('TOPIC_TAG_SLUG', 'iran')

    watch_default = 'Reuters,cnnbrk,EnglishFars,IranIntl_En,BBCBreaking'
    watch_users_raw = _input_default('WATCH_USERS (comma-separated)', watch_default)
    watch_users = [x.strip() for x in watch_users_raw.split(',') if x.strip()]

    max_asset_usd = float(_input_default('MAX_ASSET_USD', '10'))
    min_trade_usdc = float(_input_default('MIN_TRADE_USDC', '5'))
    max_trade_usdc = float(_input_default('MAX_TRADE_USDC', str(max_asset_usd)))

    market_refresh_interval = int(_input_default('MARKET_REFRESH_INTERVAL_SECONDS', '86400'))
    twitter_poll_interval = int(_input_default('TWITTER_POLL_INTERVAL_SECONDS', '60'))
    volume_min = int(_input_default('VOLUME_MIN', '1000000'))
    rag_score_threshold = float(_input_default('RAG_SCORE_THRESHOLD', '0.70'))
    decision_enabled = _input_bool('DECISION_ENABLED', True)
    trading_enabled = _input_bool('TRADING_ENABLED', True)

    openclaw_command = ['openclaw', 'agent', '--message']
    trusted_media = ['Reuters', 'AP', 'BBCWorld', 'Bloomberg']
    twitter_auth_token = _input_default('TWITTER_AUTH_TOKEN', '')
    twitter_ct0 = _input_default('TWITTER_CT0', '')

    task_dir = TASKS_ROOT / task_name
    (task_dir / 'data').mkdir(parents=True, exist_ok=True)
    (task_dir / 'vector').mkdir(parents=True, exist_ok=True)
    (task_dir / 'logs').mkdir(parents=True, exist_ok=True)
    (task_dir / 'test').mkdir(parents=True, exist_ok=True)

    (task_dir / 'task_config.py').write_text(
        TASK_CONFIG_TEMPLATE.format(
            task_name=task_name,
            max_asset_usd=max_asset_usd,
            min_trade_usdc=min_trade_usdc,
            max_trade_usdc=max_trade_usdc,
            init_time=datetime.now(timezone.utc).isoformat(),
            market_refresh_interval=market_refresh_interval,
            twitter_poll_interval=twitter_poll_interval,
            watch_users=watch_users,
            tag_slug=tag_slug,
            volume_min=volume_min,
            rag_score_threshold=rag_score_threshold,
            decision_enabled=decision_enabled,
            trading_enabled=trading_enabled,
            openclaw_command=openclaw_command,
            trusted_media=trusted_media,
            twitter_auth_token=twitter_auth_token,
            twitter_ct0=twitter_ct0,
        ),
        encoding='utf-8',
    )

    print(f'[OK] Created task: {task_dir}')
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

    log_dir = task_dir / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_file = (log_dir / 'start_stdout.log').open('a', encoding='utf-8')

    cmd = [sys.executable, '-m', 'polyagent.cli', 'run', '--task', task_name, '--daemon']
    proc = subprocess.Popen(cmd, start_new_session=True, stdout=stdout_file, stderr=subprocess.STDOUT)

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
        if alive:
            row = {**meta, 'alive': alive}
            rows.append(row)
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
