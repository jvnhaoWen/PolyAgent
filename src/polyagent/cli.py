from __future__ import annotations

import argparse
import asyncio
import logging

from .tasking import create_task_interactive, list_tasks, start_task_process, stop_task


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='poly-monitor', description='PolyAgent task manager')
    sub = p.add_subparsers(dest='command', required=True)

    sub.add_parser('new', help='Create a new task config')

    run = sub.add_parser('run', help='Run one task in current process (infinite)')
    run.add_argument('--task', required=True)

    start = sub.add_parser('start', help='Start one task in background process')
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
        from .runtime import PolyMonitorRuntime
        runtime = PolyMonitorRuntime(args.task)
        asyncio.run(runtime.run_forever())
        return


if __name__ == '__main__':
    main()
