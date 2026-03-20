from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from .dashboard import run_dashboard
from .tasking import create_task_interactive, list_tasks, start_task_process, stop_task


LOGO = r"""
██████╗  ██████╗ ██╗  ██╗   ██╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗
██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
██████╔╝██║   ██║██║   ╚████╔╝     ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
██╔═══╝ ██║   ██║██║    ╚██╔╝      ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
██║     ╚██████╔╝███████╗██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
╚═╝      ╚═════╝ ╚══════╝╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
"""


def _package_version() -> str:
    try:
        return version('polyagent')
    except PackageNotFoundError:
        return 'dev'


def print_logo() -> None:
    started = datetime.now(timezone.utc).isoformat()
    ver = _package_version()

    if not sys.stdout.isatty():
        print(LOGO)
        print(f"POLY MONITOR v{ver} started at {started} (UTC)\n")
        return

    reset = "\033[0m"
    colors = ["\033[38;5;45m", "\033[38;5;51m", "\033[38;5;87m", "\033[38;5;123m", "\033[38;5;159m", "\033[38;5;195m"]

    lines = LOGO.strip("\n").splitlines()
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        print(f"{color}{line}{reset}")

    print(f"\033[38;5;48mPOLY MONITOR v{ver} started at {started} (UTC)\033[0m\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='poly-monitor', description='PolyAgent task manager')
    sub = p.add_subparsers(dest='command', required=True)

    sub.add_parser('new', help='Create a new task config')

    run = sub.add_parser('run', help='Run one task in current process (infinite)')
    run.add_argument('--task', required=True)
    run.add_argument('--mode', choices=['test', 'background'], default='test', help=argparse.SUPPRESS)

    start = sub.add_parser('start', help='Start one task in background process and open dashboard')
    start.add_argument('--task', required=True)

    sub.add_parser('list', help='List running tasks')

    stop = sub.add_parser('stop', help='Stop background task by task name')
    stop.add_argument('--task', required=True)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    if args.command == 'new':
        create_task_interactive()
        return

    if args.command == 'start':
        pid = start_task_process(args.task)
        print(f'[OK] started task={args.task} pid={pid}')
        try:
            run_dashboard(args.task)
        except KeyboardInterrupt:
            print('\n[OK] dashboard exited, background task is still running')
        return

    if args.command == 'list':
        rows = list_tasks()
        if not rows:
            print('No running tasks')
            return

        for r in rows:
            print(f"task={r['task_name']} pid={r['pid']} alive={r['alive']} started_at={r['started_at']}")
        return

    if args.command == 'stop':
        ok = stop_task(args.task)
        print('[OK] stopped' if ok else '[WARN] task not found')
        return

    if args.command == 'run':
        if args.mode == 'test':
            print_logo()

        from .runtime import PolyMonitorRuntime

        runtime = PolyMonitorRuntime(args.task, mode=args.mode)
        asyncio.run(runtime.run_forever())
        return


if __name__ == '__main__':
    main()
