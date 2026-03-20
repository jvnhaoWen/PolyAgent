from __future__ import annotations

import json
import os
import re
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

RESET = '\033[0m'
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
SECTION_STYLES = {
    'header': {'border': '\033[38;5;81m', 'title': '\033[1;38;5;117m', 'text': '\033[38;5;252m'},
    'portfolio': {'border': '\033[38;5;114m', 'title': '\033[1;38;5;120m', 'text': '\033[38;5;255m'},
    'news': {'border': '\033[38;5;221m', 'title': '\033[1;38;5;228m', 'text': '\033[38;5;255m'},
}
HEARTBEAT_PALETTE = [
    '\033[1;38;5;45m●\033[0m',
    '\033[1;38;5;51m●\033[0m',
    '\033[1;38;5;87m●\033[0m',
    '\033[1;38;5;123m●\033[0m',
    '\033[1;38;5;159m●\033[0m',
    '\033[1;38;5;195m●\033[0m',
]
SECTION_WIDTH = 112
SECTION_HEIGHTS = {
    'header': 13,
    'portfolio': 24,
    'news': 18,
}


class PolyMonitorDashboard:
    def __init__(self, task_name: str, refresh_seconds: int = 1) -> None:
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
        self._wallet_cache: tuple[float, tuple[str, str]] | None = None
        self._portfolio_cache: tuple[float, list[str]] | None = None

    def _clear(self) -> None:
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

    def _move_to_top(self) -> None:
        sys.stdout.write('\033[H')
        sys.stdout.flush()

    def _heartbeat(self) -> str:
        return HEARTBEAT_PALETTE[int(time.time()) % len(HEARTBEAT_PALETTE)]

    def _read_private_key(self) -> str | None:
        config_key = str(self.cfg.get('POLYMARKET_PRIVATE_KEY', '')).strip()
        if config_key:
            return config_key

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
        if self._wallet_cache and (time.time() - self._wallet_cache[0] < 30):
            return self._wallet_cache[1]

        private_key = self._read_private_key()
        if not private_key:
            result = ('N/A', 'N/A')
            self._wallet_cache = (time.time(), result)
            return result

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
        result = (eoa, proxy_wallet)
        self._wallet_cache = (time.time(), result)
        return result

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

    def _format_ts(self, value: Any) -> str:
        if value in (None, ''):
            return 'N/A'
        if isinstance(value, (int, float)):
            try:
                stamp = float(value)
                if stamp > 10_000_000_000:
                    stamp /= 1000
                return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            except Exception:
                return str(value)
        text = str(value)
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception:
            return text

    def _truncate(self, value: Any, width: int) -> str:
        text = str(value).replace('\n', ' ').strip()
        if len(text) <= width:
            return text
        return f'{text[: width - 1]}…'

    def _format_money(self, value: Any) -> str:
        try:
            return f'${float(value):,.2f}'
        except Exception:
            return str(value)

    def _portfolio_lines(self, eoa: str, proxy_wallet: str) -> list[str]:
        if self._portfolio_cache and (time.time() - self._portfolio_cache[0] < 30):
            return self._portfolio_cache[1]

        if proxy_wallet == 'N/A':
            lines = [
                'Wallet status : Missing private key',
                'Fix           : Fill POLYMARKET_PRIVATE_KEY during `poly-monitor new`,',
                '                or set POLY_PRIVATE_KEY / POLYMARKET_PRIVATE_KEY,',
                '                or provide tasks/<task>/private_key.txt.',
            ]
            self._portfolio_cache = (time.time(), lines)
            return lines

        body_width = SECTION_WIDTH - 2
        lines = [
            f'EOA address   : {self._truncate(eoa, body_width - 16)}',
            f'Proxy wallet  : {self._truncate(proxy_wallet, body_width - 16)}',
            '',
        ]
        try:
            value_data = requests.get(
                'https://data-api.polymarket.com/value',
                params={'user': proxy_wallet},
                timeout=20,
            ).json()
            lines.append('Portfolio value summary')
            if isinstance(value_data, list):
                for item in value_data:
                    if not isinstance(item, dict):
                        continue
                    for key, value in item.items():
                        label = key.replace('Value', ' Value').replace('_', ' ').strip().title()
                        display = self._format_money(value) if any(t in key.lower() for t in ('value', 'balance', 'profit')) else value
                        lines.append(f'  • {label:<22} {display}')
            elif isinstance(value_data, dict):
                for key, value in value_data.items():
                    label = key.replace('_', ' ').strip().title()
                    display = self._format_money(value) if any(t in key.lower() for t in ('value', 'balance', 'profit')) else value
                    lines.append(f'  • {label:<22} {display}')
            else:
                lines.append('  • No portfolio summary available')
        except Exception as exc:
            lines.append(f'Portfolio fetch failed: {exc}')

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
            lines.append('Recent activity')
            if isinstance(activity, list) and activity:
                for row in activity[:4]:
                    if not isinstance(row, dict):
                        continue
                    timestamp = self._format_ts(row.get('timestamp'))
                    side = str(row.get('side', 'N/A')).upper()
                    action = str(row.get('type', 'N/A')).upper()
                    price = float(row.get('price', 0.0) or 0.0)
                    usdc = float(row.get('usdcSize', 0.0) or 0.0)
                    market = self._truncate(
                        f"{row.get('title', 'Unknown')} ({str(row.get('outcome', '')).strip() or 'N/A'})",
                        body_width - 12,
                    )
                    lines.append(f'  • {timestamp} | {action:<8} | {side:<4} | {price:>5.3f} | {usdc:>8.2f} USDC')
                    lines.append(f'    {market}')
            else:
                lines.append('  • No recent activity found')
        except Exception as exc:
            lines.append(f'Activity fetch failed: {exc}')

        lines.append('')
        try:
            positions = requests.get(
                'https://data-api.polymarket.com/positions',
                params={'user': proxy_wallet, 'sizeThreshold': 0.01},
                timeout=20,
            ).json()
            lines.append('Open positions')
            if isinstance(positions, list) and positions:
                for row in positions[:4]:
                    if not isinstance(row, dict):
                        continue
                    label = self._truncate(
                        f"{row.get('title', 'Unknown')} ({str(row.get('outcome', '')).strip() or 'N/A'})",
                        body_width - 20,
                    )
                    size = float(row.get('size', 0) or 0)
                    price = float(row.get('price', 0) or 0)
                    lines.append(f'  • {label}')
                    lines.append(f'    Size: {size:.2f} | Avg price: {price:.3f}')
            else:
                lines.append('  • No open positions found')
        except Exception as exc:
            lines.append(f'Position fetch failed: {exc}')

        self._portfolio_cache = (time.time(), lines)
        return lines

    def _news_lines(self) -> list[str]:
        tweets = self._safe_jsonl_rows(self.paths['tweets'])
        if not tweets:
            return ['No tweets captured yet.']

        body_width = SECTION_WIDTH - 2
        lines = ['Latest news stream']
        for index, tweet in enumerate(reversed(tweets[-4:]), start=1):
            user = tweet.get('user', 'unknown')
            created_at = self._format_ts(tweet.get('created_at'))
            url = tweet.get('url') or 'N/A'
            text = self._truncate(tweet.get('text', ''), body_width - 6)
            lines.append(f'{index}. @{user} · {created_at}')
            lines.append(f'   {text}')
            lines.append(f'   Link: {self._truncate(url, body_width - 9)}')
            if index != min(4, len(tweets)):
                lines.append('')
        return lines

    def _header_lines(self) -> list[str]:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        init_time = str(self.cfg.get('TASK_INIT_TIME', 'N/A'))
        stats = self._stats()
        colors = ['\033[38;5;255m', '\033[38;5;252m', '\033[38;5;250m']
        lines = [f"{colors[i % len(colors)]}{line}{RESET}" for i, line in enumerate(DASHBOARD_LOGO)]
        lines.extend(
            [
                '',
                f'Task name     : {self.task_name}',
                'Version       : 1.1.0',
                f'Init time     : {init_time}',
                f'Current time  : {now}',
                f'Heartbeat     : {self._heartbeat()}',
                f'Decisions     : {stats["transactions"]}',
                f'Triggered news: {stats["triggered_news"]}',
                f'Tweets cached : {stats["tweets"]}',
            ]
        )
        return lines

    def _visible_len(self, value: str) -> int:
        return len(ANSI_RE.sub('', value))

    def _pad_visible(self, value: str, width: int) -> str:
        padding = max(width - self._visible_len(value), 0)
        return value + (' ' * padding)

    def _normalize_section_lines(self, lines: list[str], style_name: str) -> list[str]:
        visible_width = SECTION_WIDTH
        max_lines = SECTION_HEIGHTS[style_name]
        normalized = [self._pad_visible(self._truncate(line, visible_width), visible_width) for line in lines[:max_lines]]
        while len(normalized) < max_lines:
            normalized.append(' ' * visible_width)
        return normalized

    def _box_section(self, title: str, lines: list[str], style_name: str) -> str:
        style = SECTION_STYLES[style_name]
        border = style['border']
        title_color = style['title']
        text_color = style['text']
        normalized = self._normalize_section_lines(lines, style_name)
        top = f"{border}╭{'─' * (SECTION_WIDTH + 2)}╮{RESET}"
        title_line = f"{border}│{RESET} {title_color}{title.ljust(SECTION_WIDTH)}{RESET} {border}│{RESET}"
        divider = f"{border}├{'─' * (SECTION_WIDTH + 2)}┤{RESET}"
        body = [f"{border}│{RESET} {text_color}{line}{RESET} {border}│{RESET}" for line in normalized]
        bottom = f"{border}╰{'─' * (SECTION_WIDTH + 2)}╯{RESET}"
        return '\n'.join([top, title_line, divider, *body, bottom])

    def render(self) -> str:
        eoa, proxy_wallet = self._wallet_summary()
        blocks = [
            self._box_section('SYSTEM STATUS', self._header_lines(), 'header'),
            self._box_section('PORTFOLIO OVERVIEW', self._portfolio_lines(eoa, proxy_wallet), 'portfolio'),
            self._box_section('NEWS FEED', self._news_lines(), 'news'),
        ]
        return '\n\n'.join(blocks)

    def loop(self) -> None:
        first_frame = True
        while True:
            self.cfg = load_task_config(self.task_dir)
            frame = self.render()
            if first_frame:
                self._clear()
                print(frame, end='')
                first_frame = False
            else:
                self._move_to_top()
                print(frame, end='')
            sys.stdout.flush()
            time.sleep(self.refresh_seconds)


def run_dashboard(task_name: str) -> None:
    PolyMonitorDashboard(task_name).loop()
