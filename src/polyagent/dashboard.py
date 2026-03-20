from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from .tasking import load_task_config


DASHBOARD_LOGO = [
    '██████╗  ██████╗ ██╗  ██╗   ██╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗',
    '██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗',
    '██████╔╝██║   ██║██║   ╚████╔╝     ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝',
    '██╔═══╝ ██║   ██║██║    ╚██╔╝      ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗',
    '██║     ╚██████╔╝███████╗██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║',
    '╚═╝      ╚═════╝ ╚══════╝╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝',
]


class PolyMonitorDashboard:
    def __init__(self, task_name: str, refresh_seconds: int = 60) -> None:
        self.task_name = task_name
        self.task_dir = Path('tasks') / task_name
        self.cfg = load_task_config(self.task_dir)
        self.refresh_seconds = refresh_seconds
        self.paths = {
            'tweets': self.task_dir / 'data' / 'tweets.jsonl',
            'runtime': self.task_dir / 'logs' / 'runtime_events.jsonl',
            'decision_records': self.task_dir / 'test' / 'decision_records.jsonl',
            'private_key_task': self.task_dir / 'private_key.txt',
            'private_key_root': Path('.private_key'),
        }

    def _clear(self) -> None:
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

    def _heartbeat(self) -> str:
        palette = ['\033[38;5;51m●\033[0m', '\033[38;5;87m●\033[0m', '\033[38;5;123m●\033[0m', '\033[38;5;159m●\033[0m']
        return palette[int(time.time()) % len(palette)]

    def _read_private_key(self) -> str | None:
        for key in ('POLY_PRIVATE_KEY', 'POLYMARKET_PRIVATE_KEY', 'PRIVATE_KEY'):
            value = os.environ.get(key, '').strip()
            if value:
                return value

        for path in (self.paths['private_key_task'], self.paths['private_key_root']):
            if path.exists():
                value = path.read_text(encoding='utf-8').strip()
                if value:
                    return value
        return None

    def _wallet_summary(self) -> tuple[str, str]:
        private_key = self._read_private_key()
        if not private_key:
            return 'N/A', 'N/A'

        from eth_account import Account

        eoa = Account.from_key(private_key).address
        try:
            profile_resp = requests.get(
                'https://gamma-api.polymarket.com/public-profile',
                params={'address': eoa},
                timeout=20,
            )
            profile = profile_resp.json()
            proxy_wallet = profile.get('proxyWallet') or eoa
        except Exception:
            proxy_wallet = eoa
        return eoa, proxy_wallet

    def _safe_jsonl_rows(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open('r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except Exception:
            return []
        return rows

    def _stats(self) -> dict[str, int]:
        runtime_rows = self._safe_jsonl_rows(self.paths['runtime'])
        tweets_rows = self._safe_jsonl_rows(self.paths['tweets'])
        transactions = sum(1 for row in runtime_rows if row.get('type') == 'decision')
        triggered_news = sum(1 for row in runtime_rows if row.get('type') == 'trigger_record')
        return {
            'transactions': transactions,
            'triggered_news': triggered_news,
            'tweets': len(tweets_rows),
        }

    def _portfolio_lines(self, eoa: str, proxy_wallet: str) -> list[str]:
        if proxy_wallet == 'N/A':
            return ['Private key not found. Set POLY_PRIVATE_KEY / POLYMARKET_PRIVATE_KEY or provide private_key.txt.']

        lines = [f"EOA Address: {eoa}", f"Proxy Wallet: {proxy_wallet}", '=' * 60, '']
        try:
            value_data = requests.get(
                'https://data-api.polymarket.com/value',
                params={'user': proxy_wallet},
                timeout=20,
            ).json()
            lines.append('[ Portfolio Value Summary ]')
            if isinstance(value_data, list):
                for item in value_data:
                    if not isinstance(item, dict):
                        continue
                    for k, v in item.items():
                        label = k.replace('Value', ' Value').title()
                        lines.append(f' - {label}: {v}')
            elif isinstance(value_data, dict):
                for k, v in value_data.items():
                    lines.append(f' - {k.title()}: {v}')
            else:
                lines.append(' - No portfolio summary available')
        except Exception as exc:
            lines.append(f'Failed to fetch portfolio value: {exc}')

        lines.append('')
        try:
            activity = requests.get(
                'https://data-api.polymarket.com/activity',
                params={
                    'user': proxy_wallet,
                    'limit': 15,
                    'sortBy': 'TIMESTAMP',
                    'sortDirection': 'DESC',
                },
                timeout=20,
            ).json()
            lines.append('[ Recent Activity (Last 10) ]')
            header = f"{'Time':<18} | {'Type':<8} | {'Side':<5} | {'Price':<6} | {'USDC Size':<10} | Market"
            lines.append(header)
            lines.append('-' * len(header))
            if isinstance(activity, list):
                for row in activity[:10]:
                    if not isinstance(row, dict):
                        continue
                    timestamp = row.get('timestamp')
                    dt_str = 'N/A'
                    if timestamp:
                        try:
                            dt_str = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            dt_str = str(timestamp)[:16]
                    price = float(row.get('price', 0.0) or 0.0)
                    usdc = float(row.get('usdcSize', 0.0) or 0.0)
                    title = str(row.get('title', 'Unknown'))
                    outcome = str(row.get('outcome', '')).strip()
                    market_label = f'{title} ({outcome})' if outcome else title
                    lines.append(
                        f"{dt_str:<18} | {str(row.get('type', 'N/A')):<8} | {str(row.get('side', 'N/A')):<5} | {price:<6.3f} | {usdc:<10.2f} | {market_label}"
                    )
            else:
                lines.append('No recent activity found')
        except Exception as exc:
            lines.append(f'Failed to fetch activity: {exc}')

        lines.append('')
        try:
            positions = requests.get(
                'https://data-api.polymarket.com/positions',
                params={'user': proxy_wallet, 'sizeThreshold': 0.01},
                timeout=20,
            ).json()
            if isinstance(positions, list) and positions:
                lines.append('[ Open Positions ]')
                header = f"{'Asset / Market':<50} | {'Size':<10} | Avg Price"
                lines.append(header)
                lines.append('-' * len(header))
                for row in positions:
                    if not isinstance(row, dict):
                        continue
                    title = str(row.get('title', 'Unknown'))
                    outcome = str(row.get('outcome', '')).strip()
                    label = f'{title} ({outcome})' if outcome else title
                    size = float(row.get('size', 0) or 0)
                    price = float(row.get('price', 0) or 0)
                    lines.append(f"{label:<50} | {size:<10.2f} | {price:.3f}")
            else:
                lines.append('[ No open positions found ]')
        except Exception as exc:
            lines.append(f'Failed to fetch positions: {exc}')
        return lines

    def _news_lines(self) -> list[str]:
        tweets = self._safe_jsonl_rows(self.paths['tweets'])
        if not tweets:
            return ['No tweets captured yet.']

        lines = ['[ Latest News Stream ]']
        for tweet in tweets[-5:]:
            lines.append(json.dumps(tweet, ensure_ascii=False))
        return lines

    def _header_lines(self) -> list[str]:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        init_time = str(self.cfg.get('TASK_INIT_TIME', 'N/A'))
        version = '1.1.0'
        stats = self._stats()
        lines: list[str] = []
        colors = ['\033[38;5;255m', '\033[38;5;252m', '\033[38;5;250m']
        reset = '\033[0m'
        for i, line in enumerate(DASHBOARD_LOGO):
            lines.append(f"{colors[i % len(colors)]}{line}{reset}")
        lines.append(
            f"version {version} | init time {init_time} | now {now} | heartbeat {self._heartbeat()} | transactions/triggered news: {stats['transactions']}/{stats['triggered_news']}"
        )
        return lines

    def render(self) -> str:
        eoa, proxy_wallet = self._wallet_summary()
        portfolio_lines = self._portfolio_lines(eoa, proxy_wallet)

        blocks = [
            '\n'.join(self._header_lines()),
            '\n'.join(portfolio_lines),
            '\n'.join(self._news_lines()),
        ]
        separator = '\n' + ('=' * 100) + '\n'
        return separator.join(blocks)

    def loop(self) -> None:
        while True:
            self.cfg = load_task_config(self.task_dir)
            self._clear()
            print(self.render())
            sys.stdout.flush()
            time.sleep(self.refresh_seconds)


def run_dashboard(task_name: str) -> None:
    PolyMonitorDashboard(task_name).loop()
