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


TASK_MD_TEMPLATE = """# Task.md

你是一个 7*24h 运行的 Polymarket 推特监控交易 Agent。

你的主要任务：
1. 基于 task_config.py 读取监控参数。
2. 监控 WATCH_USERS 的实时推特更新。
3. 将新闻与 Polymarket 市场做向量匹配。
4. 当匹配分数满足阈值时，生成交易决策提示词并调用 OpenClaw。
5. 严格遵守 MAX_ASSET_USD 风险约束。
6. 记录每一次触发、匹配、决策与下单结果到 test/ 与 logs/。

启动后请先确认：
- 监控主题 TOPIC_TAG_SLUG
- 每次可用最大资金 MAX_ASSET_USD
- 是否启用 DECISION_ENABLED / TRADING_ENABLED
"""


TASK_CONFIG_TEMPLATE = """TASK_NAME = {task_name!r}
MAX_ASSET_USD = {max_asset_usd}
TASK_INIT_TIME = {task_init_time!r}
MARKET_REFRESH_INTERVAL_SECONDS = {refresh_seconds}
TWITTER_POLL_INTERVAL_SECONDS = {twitter_poll}
WATCH_USERS = {watch_users!r}
TOPIC_TAG_SLUG = {tag_slug!r}
VOLUME_MIN = {volume_min}
RAG_SCORE_THRESHOLD = {rag_threshold}
RAG_TOP_K = {rag_top_k}
DECISION_ENABLED = {decision_enabled}
TRADING_ENABLED = {trading_enabled}
OPENCLAW_COMMAND = {openclaw_command!r}
TRUSTED_MEDIA = {trusted_media!r}
"""


@dataclass(slots=True)
class TaskMeta:
    task_name: str
    pid: int
    started_at: str
    cmd: list[str]


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
    TASKS_ROOT.mkdir(parents=True, exist_ok=True)

    task_name = input('Task name (e.g. iran_fast_reaction): ').strip() or 'default_task'
    tag_slug = input('Topic tag_slug (e.g. iran): ').strip() or 'iran'
    max_asset_usd = float(input('MAX_ASSET_USD [10]: ').strip() or '10')

    watch_users_raw = input('WATCH_USERS comma-separated [Reuters,AP,BBCWorld]: ').strip() or 'Reuters,AP,BBCWorld'
    watch_users = [x.strip() for x in watch_users_raw.split(',') if x.strip()]

    volume_min = int(input('VOLUME_MIN [1000000]: ').strip() or '1000000')
    rag_threshold = float(input('RAG_SCORE_THRESHOLD [0.70]: ').strip() or '0.70')

    task_dir = TASKS_ROOT / task_name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / 'data').mkdir(exist_ok=True)
    (task_dir / 'vector').mkdir(exist_ok=True)
    (task_dir / 'logs').mkdir(exist_ok=True)
    (task_dir / 'test').mkdir(exist_ok=True)

    (task_dir / 'task.md').write_text(TASK_MD_TEMPLATE, encoding='utf-8')
    config_text = TASK_CONFIG_TEMPLATE.format(
        task_name=task_name,
        max_asset_usd=max_asset_usd,
        task_init_time=datetime.now(timezone.utc).isoformat(),
        refresh_seconds=86400,
        twitter_poll=60,
        watch_users=watch_users,
        tag_slug=tag_slug,
        volume_min=volume_min,
        rag_threshold=rag_threshold,
        rag_top_k=5,
        decision_enabled=True,
        trading_enabled=True,
        openclaw_command=['openclaw', 'agent', '--message'],
        trusted_media=['Reuters', 'AP', 'BBCWorld', 'Bloomberg'],
    )
    (task_dir / 'task_config.py').write_text(config_text, encoding='utf-8')

    print(f'[OK] Task created: {task_dir}')
    return task_dir


def load_task_config(task_dir: Path) -> dict[str, Any]:
    cfg_path = task_dir / 'task_config.py'
    if not cfg_path.exists():
        raise FileNotFoundError(f'missing task_config.py: {cfg_path}')

    spec = importlib.util.spec_from_file_location(f'task_config_{task_dir.name}', cfg_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load {cfg_path}')

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return {
        k: getattr(module, k)
        for k in dir(module)
        if k.isupper()
    }


def start_task_process(task_name: str) -> int:
    task_dir = TASKS_ROOT / task_name
    if not task_dir.exists():
        raise FileNotFoundError(f'task not found: {task_name}')

    cmd = [sys.executable, '-m', 'polyagent.cli', 'run', '--task', task_name]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    registry = _load_registry()
    registry[task_name] = asdict(TaskMeta(
        task_name=task_name,
        pid=proc.pid,
        started_at=datetime.now(timezone.utc).isoformat(),
        cmd=cmd,
    ))
    _save_registry(registry)
    return proc.pid


def list_tasks() -> list[dict[str, Any]]:
    registry = _load_registry()
    results: list[dict[str, Any]] = []
    changed = False

    for task_name, meta in registry.items():
        pid = int(meta.get('pid', -1))
        alive = _is_alive(pid)
        item = dict(meta)
        item['alive'] = alive
        results.append(item)
        if not alive:
            changed = True

    if changed:
        cleaned = {x['task_name']: x for x in results if x['alive']}
        _save_registry(cleaned)

    return results


def stop_task(task_name: str) -> bool:
    registry = _load_registry()
    meta = registry.get(task_name)
    if not meta:
        return False

    pid = int(meta['pid'])
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    registry.pop(task_name, None)
    _save_registry(registry)
    return True
