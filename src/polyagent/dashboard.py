from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .tasking import load_task_config

DASHBOARD_LOGO = [
    '██████╗  ██████╗ ██╗  ██╗   ██╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗',
    '██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗',
    '██████╔╝██║   ██║██║   ╚████╔╝     ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝',
    '██╔═══╝ ██║   ██║██║    ╚██╔╝      ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗',
    '██║     ╚██████╔╝███████╗██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║',
    '╚═╝      ╚═════╝ ╚══════╝╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝',
]

VERSION = '1.2.0'
HTTP_TIMEOUT = 20
WALLET_CACHE_TTL = 30
PORTFOLIO_CACHE_TTL = 30
MAX_ACTIVITY_ROWS = 6
MAX_POSITION_ROWS = 6
MAX_NEWS_ITEMS = 5

_CAMEL_RE_1 = re.compile(r'(.)([A-Z][a-z]+)')
_CAMEL_RE_2 = re.compile(r'([a-z0-9])([A-Z])')


@dataclass(slots=True)
class Stats:
    decisions: int = 0
    triggered_news: int = 0
    tweets: int = 0


@dataclass(slots=True)
class ActivityItem:
    timestamp: str
    action: str
    side: str
    price: str
    usdc: str
    market: str


@dataclass(slots=True)
class PositionItem:
    market: str
    size: str
    avg_price: str


@dataclass(slots=True)
class NewsItem:
    user: str
    created_at: str
    text: str
    url: str


@dataclass(slots=True)
class PortfolioData:
    eoa: str = 'N/A'
    proxy_wallet: str = 'N/A'
    summary: dict[str, str] = field(default_factory=dict)
    activity: list[ActivityItem] = field(default_factory=list)
    positions: list[PositionItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DashboardSnapshot:
    task_name: str
    version: str
    init_time: str
    now_utc: str
    heartbeat_style: str
    stats: Stats
    portfolio: PortfolioData
    news: list[NewsItem]


class PolyMonitorDashboard:
    HEARTBEAT_STYLES = [
        'bold bright_cyan',
        'bold cyan',
        'bold bright_blue',
        'bold bright_magenta',
        'bold bright_green',
        'bold bright_white',
    ]

    def __init__(self, task_name: str, refresh_seconds: int = 1) -> None:
        self.task_name = task_name
        self.task_dir = Path('tasks') / task_name
        self.cfg = load_task_config(self.task_dir)
        self.refresh_seconds = refresh_seconds

        self.paths = {
            'tweets': self.task_dir / 'data' / 'tweets.jsonl',
            'runtime': self.task_dir / 'logs' / 'runtime_events.jsonl',
            'private_key_task': self.task_dir / 'private_key.txt',
            'private_key_root': Path('.private_key'),
        }

        self.console = Console()
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'polyagent-dashboard/1.2.0'})

        self._wallet_cache: tuple[float, tuple[str, str]] | None = None
        self._portfolio_cache: tuple[float, PortfolioData] | None = None

    def _heartbeat_style(self) -> str:
        return self.HEARTBEAT_STYLES[int(time.time()) % len(self.HEARTBEAT_STYLES)]

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
                try:
                    value = path.read_text(encoding='utf-8').strip()
                except Exception:
                    continue
                if value:
                    return value

        return None

    def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return response.json()

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

    def _stats(self) -> Stats:
        runtime_rows = self._safe_jsonl_rows(self.paths['runtime'])
        tweets_rows = self._safe_jsonl_rows(self.paths['tweets'])

        return Stats(
            decisions=sum(1 for row in runtime_rows if row.get('type') == 'decision'),
            triggered_news=sum(1 for row in runtime_rows if row.get('type') == 'trigger_record'),
            tweets=len(tweets_rows),
        )

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
            return (
                datetime.fromisoformat(text.replace('Z', '+00:00'))
                .astimezone(timezone.utc)
                .strftime('%Y-%m-%d %H:%M:%S UTC')
            )
        except Exception:
            return text

    def _format_money(self, value: Any) -> str:
        try:
            return f'${float(value):,.2f}'
        except Exception:
            return str(value)

    def _format_decimal(self, value: Any, digits: int = 3) -> str:
        try:
            return f'{float(value):.{digits}f}'
        except Exception:
            return str(value)

    def _humanize_key(self, key: str) -> str:
        step1 = _CAMEL_RE_1.sub(r'\1 \2', key)
        step2 = _CAMEL_RE_2.sub(r'\1 \2', step1)
        return step2.replace('_', ' ').strip().title()

    def _short_address(self, value: str) -> str:
        if value == 'N/A' or len(value) < 18:
            return value
        return f'{value[:10]}…{value[-8:]}'

    def _wallet_summary(self) -> tuple[str, str]:
        if self._wallet_cache and (time.time() - self._wallet_cache[0] < WALLET_CACHE_TTL):
            return self._wallet_cache[1]

        private_key = self._read_private_key()
        if not private_key:
            result = ('N/A', 'N/A')
            self._wallet_cache = (time.time(), result)
            return result

        from eth_account import Account

        eoa = Account.from_key(private_key).address
        proxy_wallet = eoa

        try:
            profile = self._get_json(
                'https://gamma-api.polymarket.com/public-profile',
                params={'address': eoa},
            )
            if isinstance(profile, dict):
                proxy_wallet = str(profile.get('proxyWallet') or eoa)
        except Exception:
            proxy_wallet = eoa

        result = (eoa, proxy_wallet)
        self._wallet_cache = (time.time(), result)
        return result

    def _extract_summary(self, value_data: Any) -> dict[str, str]:
        result: dict[str, str] = {}

        def put_items(obj: dict[str, Any]) -> None:
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    continue
                label = self._humanize_key(str(key))
                lowered = str(key).lower()
                if any(token in lowered for token in ('value', 'balance', 'profit', 'pnl', 'usdc')):
                    result[label] = self._format_money(value)
                else:
                    result[label] = str(value)

        if isinstance(value_data, dict):
            put_items(value_data)
        elif isinstance(value_data, list):
            for item in value_data:
                if isinstance(item, dict):
                    put_items(item)

        return result

    def _fetch_portfolio(self, eoa: str, proxy_wallet: str) -> PortfolioData:
        if self._portfolio_cache and (time.time() - self._portfolio_cache[0] < PORTFOLIO_CACHE_TTL):
            return self._portfolio_cache[1]

        portfolio = PortfolioData(eoa=eoa, proxy_wallet=proxy_wallet)

        if proxy_wallet == 'N/A':
            portfolio.notes.extend(
                [
                    'Wallet status: missing private key.',
                    'Fill POLYMARKET_PRIVATE_KEY in task config,',
                    'or set POLY_PRIVATE_KEY / POLYMARKET_PRIVATE_KEY in env,',
                    'or create tasks/<task>/private_key.txt.',
                ]
            )
            self._portfolio_cache = (time.time(), portfolio)
            return portfolio

        try:
            value_data = self._get_json(
                'https://data-api.polymarket.com/value',
                params={'user': proxy_wallet},
            )
            portfolio.summary = self._extract_summary(value_data)
            if not portfolio.summary:
                portfolio.notes.append('No portfolio summary available.')
        except Exception as exc:
            portfolio.notes.append(f'Portfolio summary fetch failed: {exc}')

        try:
            activity_data = self._get_json(
                'https://data-api.polymarket.com/activity',
                params={
                    'user': proxy_wallet,
                    'limit': 15,
                    'sortBy': 'TIMESTAMP',
                    'sortDirection': 'DESC',
                },
            )
            if isinstance(activity_data, list):
                for row in activity_data[:MAX_ACTIVITY_ROWS]:
                    if not isinstance(row, dict):
                        continue
                    portfolio.activity.append(
                        ActivityItem(
                            timestamp=self._format_ts(row.get('timestamp')),
                            action=str(row.get('type', 'N/A')).upper(),
                            side=str(row.get('side', 'N/A')).upper(),
                            price=self._format_decimal(row.get('price', 0), 3),
                            usdc=self._format_decimal(row.get('usdcSize', 0), 2),
                            market=f"{row.get('title', 'Unknown')} ({str(row.get('outcome', '')).strip() or 'N/A'})",
                        )
                    )
            if not portfolio.activity:
                portfolio.notes.append('No recent activity found.')
        except Exception as exc:
            portfolio.notes.append(f'Activity fetch failed: {exc}')

        try:
            positions_data = self._get_json(
                'https://data-api.polymarket.com/positions',
                params={'user': proxy_wallet, 'sizeThreshold': 0.01},
            )
            if isinstance(positions_data, list):
                for row in positions_data[:MAX_POSITION_ROWS]:
                    if not isinstance(row, dict):
                        continue
                    portfolio.positions.append(
                        PositionItem(
                            market=f"{row.get('title', 'Unknown')} ({str(row.get('outcome', '')).strip() or 'N/A'})",
                            size=self._format_decimal(row.get('size', 0), 2),
                            avg_price=self._format_decimal(row.get('price', 0), 3),
                        )
                    )
            if not portfolio.positions:
                portfolio.notes.append('No open positions found.')
        except Exception as exc:
            portfolio.notes.append(f'Position fetch failed: {exc}')

        self._portfolio_cache = (time.time(), portfolio)
        return portfolio

    def _news_items(self) -> list[NewsItem]:
        tweets = self._safe_jsonl_rows(self.paths['tweets'])
        if not tweets:
            return []

        items: list[NewsItem] = []
        for tweet in reversed(tweets[-MAX_NEWS_ITEMS:]):
            items.append(
                NewsItem(
                    user=str(tweet.get('user', 'unknown')),
                    created_at=self._format_ts(tweet.get('created_at')),
                    text=str(tweet.get('text', '')).replace('\n', ' ').strip(),
                    url=str(tweet.get('url') or 'N/A'),
                )
            )
        return items

    def _build_snapshot(self) -> DashboardSnapshot:
        eoa, proxy_wallet = self._wallet_summary()
        portfolio = self._fetch_portfolio(eoa, proxy_wallet)

        return DashboardSnapshot(
            task_name=self.task_name,
            version=VERSION,
            init_time=str(self.cfg.get('TASK_INIT_TIME', 'N/A')),
            now_utc=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            heartbeat_style=self._heartbeat_style(),
            stats=self._stats(),
            portfolio=portfolio,
            news=self._news_items(),
        )

    def _kv_table(self, rows: list[tuple[str, Any]], *, key_style: str = 'bold white') -> Table:
        table = Table.grid(expand=True)
        table.add_column(style=key_style, no_wrap=True)
        table.add_column(style='white')
        for key, value in rows:
            table.add_row(key, value)
        return table

    def _render_logo(self) -> Text:
        text = Text()
        for idx, line in enumerate(DASHBOARD_LOGO):
            style = 'bold bright_cyan' if idx < 2 else 'bold cyan'
            text.append(line, style=style)
            if idx != len(DASHBOARD_LOGO) - 1:
                text.append('\n')
        return text

    def _render_header(self, snapshot: DashboardSnapshot, width: int) -> Panel:
        show_big_logo = width >= max(len(line) for line in DASHBOARD_LOGO) + 8
        top_renderable: Any = self._render_logo() if show_big_logo else Text('POLY MONITOR', style='bold bright_cyan')

        heartbeat = Text('●', style=snapshot.heartbeat_style)
        stats_grid = self._kv_table(
            [
                ('Task', snapshot.task_name),
                ('Version', snapshot.version),
                ('Init time', snapshot.init_time),
                ('Current time', snapshot.now_utc),
                ('Heartbeat', heartbeat),
                ('Decisions', str(snapshot.stats.decisions)),
                ('Triggered news', str(snapshot.stats.triggered_news)),
                ('Tweets cached', str(snapshot.stats.tweets)),
            ]
        )

        body = Group(top_renderable, Rule(style='cyan'), stats_grid)
        return Panel(
            body,
            title='[bold bright_cyan]System Status[/bold bright_cyan]',
            border_style='bright_cyan',
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def _render_summary_panel(self, portfolio: PortfolioData) -> Panel:
        if portfolio.summary:
            table = Table(box=box.SIMPLE_HEAVY, expand=True)
            table.add_column('Metric', style='bold white')
            table.add_column('Value', style='green')
            for key in sorted(portfolio.summary.keys()):
                table.add_row(key, portfolio.summary[key])
            body: Any = table
        else:
            body = Text('No portfolio summary available.', style='yellow')

        return Panel(
            body,
            title='[bold green]Summary[/bold green]',
            border_style='green',
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_activity_panel(self, portfolio: PortfolioData) -> Panel:
        if portfolio.activity:
            table = Table(box=box.SIMPLE_HEAVY, expand=True)
            table.add_column('Time', style='dim', no_wrap=True)
            table.add_column('Action', style='cyan', no_wrap=True)
            table.add_column('Side', style='magenta', no_wrap=True)
            table.add_column('Price', justify='right', style='white', no_wrap=True)
            table.add_column('USDC', justify='right', style='green', no_wrap=True)
            table.add_column('Market', style='white', overflow='fold')

            for item in portfolio.activity:
                table.add_row(item.timestamp, item.action, item.side, item.price, item.usdc, item.market)
            body = table
        else:
            body = Text('No recent activity found.', style='yellow')

        return Panel(
            body,
            title='[bold green]Recent Activity[/bold green]',
            border_style='green',
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_positions_panel(self, portfolio: PortfolioData) -> Panel:
        if portfolio.positions:
            table = Table(box=box.SIMPLE_HEAVY, expand=True)
            table.add_column('Market', style='white', overflow='fold')
            table.add_column('Size', justify='right', style='cyan', no_wrap=True)
            table.add_column('Avg Price', justify='right', style='green', no_wrap=True)

            for item in portfolio.positions:
                table.add_row(item.market, item.size, item.avg_price)
            body = table
        else:
            body = Text('No open positions found.', style='yellow')

        return Panel(
            body,
            title='[bold green]Open Positions[/bold green]',
            border_style='green',
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_portfolio(self, portfolio: PortfolioData, width: int) -> Panel:
        wallet_grid = self._kv_table(
            [
                ('EOA', self._short_address(portfolio.eoa)),
                ('Proxy wallet', self._short_address(portfolio.proxy_wallet)),
            ]
        )

        notes_renderables: list[Any] = []
        if portfolio.notes:
            notes = Text()
            for idx, note in enumerate(portfolio.notes):
                notes.append(f'• {note}', style='yellow')
                if idx != len(portfolio.notes) - 1:
                    notes.append('\n')
            notes_renderables.extend([Rule(style='grey35'), notes])

        inner_width = max(width - 8, 80)
        if inner_width >= 180:
            lower: Any = Columns(
                [
                    self._render_summary_panel(portfolio),
                    self._render_activity_panel(portfolio),
                    self._render_positions_panel(portfolio),
                ],
                expand=True,
                equal=True,
            )
        elif inner_width >= 130:
            lower = Group(
                Columns(
                    [
                        self._render_summary_panel(portfolio),
                        self._render_positions_panel(portfolio),
                    ],
                    expand=True,
                    equal=True,
                ),
                self._render_activity_panel(portfolio),
            )
        else:
            lower = Group(
                self._render_summary_panel(portfolio),
                self._render_activity_panel(portfolio),
                self._render_positions_panel(portfolio),
            )

        body = Group(wallet_grid, Rule(style='green'), lower, *notes_renderables)
        return Panel(
            body,
            title='[bold green]Portfolio Overview[/bold green]',
            border_style='green',
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def _render_news(self, news: list[NewsItem]) -> Panel:
        if not news:
            return Panel(
                Text('No tweets captured yet.', style='yellow'),
                title='[bold yellow]News Feed[/bold yellow]',
                border_style='yellow',
                box=box.ROUNDED,
                padding=(1, 2),
            )

        parts: list[Any] = []
        for idx, item in enumerate(news):
            header = Text()
            header.append(f'@{item.user}', style='bold yellow')
            header.append('  ')
            header.append(item.created_at, style='dim')
            body = Text(item.text or '(empty)', style='white')
            link = Text(item.url, style='cyan')
            parts.extend([header, body, link])
            if idx != len(news) - 1:
                parts.append(Rule(style='grey35'))

        return Panel(
            Group(*parts),
            title='[bold yellow]News Feed[/bold yellow]',
            border_style='yellow',
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def render(self) -> Layout:
        snapshot = self._build_snapshot()
        width = self.console.size.width

        layout = Layout(name='root')
        layout.split_column(
            Layout(name='header', size=14 if width >= 120 else 10),
            Layout(name='body'),
        )

        if width >= 160:
            layout['body'].split_row(
                Layout(name='portfolio', ratio=2),
                Layout(name='news', ratio=1),
            )
        else:
            layout['body'].split_column(
                Layout(name='portfolio', ratio=3),
                Layout(name='news', ratio=2),
            )

        layout['header'].update(self._render_header(snapshot, width))
        layout['portfolio'].update(self._render_portfolio(snapshot.portfolio, width))
        layout['news'].update(self._render_news(snapshot.news))
        return layout

    def loop(self) -> None:
        with Live(
            self.render(),
            console=self.console,
            screen=True,
            auto_refresh=False,
            transient=False,
        ) as live:
            while True:
                self.cfg = load_task_config(self.task_dir)
                live.update(self.render(), refresh=True)
                time.sleep(self.refresh_seconds)


def run_dashboard(task_name: str) -> None:
    PolyMonitorDashboard(task_name).loop()
