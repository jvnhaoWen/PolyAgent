from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .market import MarketConfig, MarketPipeline
from .rag import EventRAG
from .tasking import load_task_config
from .trading import SimplePolymarketTrader, parse_trade_action_from_openclaw


@dataclass(slots=True)
class TaskRuntimePaths:
    task_dir: Path
    events_jsonl: Path
    filtered_events_jsonl: Path
    tweet_jsonl: Path
    last_seen_json: Path
    vector_dir: Path
    decision_records_jsonl: Path
    trade_log_jsonl: Path
    task_md: Path
    decision_md: Path


class PolyMonitorRuntime:
    def __init__(self, task_name: str) -> None:
        task_dir = Path('tasks') / task_name
        cfg = load_task_config(task_dir)
        self.task_name = task_name
        self.cfg = cfg
        self.paths = TaskRuntimePaths(
            task_dir=task_dir,
            events_jsonl=task_dir / 'data' / 'events.jsonl',
            filtered_events_jsonl=task_dir / 'data' / 'filtered_acceptingOrders.jsonl',
            tweet_jsonl=task_dir / 'data' / 'tweets.jsonl',
            last_seen_json=task_dir / 'data' / 'last_seen.json',
            vector_dir=task_dir / 'vector',
            decision_records_jsonl=task_dir / 'test' / 'decision_records.jsonl',
            trade_log_jsonl=task_dir / 'logs' / 'trades.jsonl',
            task_md=task_dir / 'task.md',
            decision_md=task_dir / 'decision.md',
        )
        self.rag = EventRAG('sentence-transformers/all-MiniLM-L6-v2')
        self.trader: SimplePolymarketTrader | None = None

    def _append_jsonl(self, path: Path, row: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    def _load_last_seen(self) -> dict[str, str]:
        if not self.paths.last_seen_json.exists():
            return {}
        try:
            return json.loads(self.paths.last_seen_json.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_last_seen(self, data: dict[str, str]) -> None:
        self.paths.last_seen_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    async def refresh_market_and_vectors(self) -> None:
        market_cfg = MarketConfig(
            tag_slug=str(self.cfg.get('TOPIC_TAG_SLUG', 'iran')),
            volume_min=int(self.cfg.get('VOLUME_MIN', 1_000_000)),
            events_jsonl=self.paths.events_jsonl,
            filtered_events_jsonl=self.paths.filtered_events_jsonl,
        )
        pipeline = MarketPipeline(market_cfg)

        events_count = await asyncio.to_thread(pipeline.scrape_events)
        filtered_count = await asyncio.to_thread(pipeline.filter_active_events)
        if filtered_count == 0:
            logging.warning('There is no matched market for your key words currently.')

        indexed = await asyncio.to_thread(self.rag.build, self.paths.filtered_events_jsonl, self.paths.vector_dir)
        logging.info('market refresh done events=%s filtered=%s indexed=%s', events_count, filtered_count, indexed)

    def _openclaw_call(self, prompt: str) -> str:
        cmd = self.cfg.get('OPENCLAW_COMMAND', ['openclaw', 'agent', '--message'])
        if not isinstance(cmd, list) or not cmd:
            raise RuntimeError('OPENCLAW_COMMAND must be list')
        proc = subprocess.run(cmd + [prompt], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f'openclaw failed: {proc.stderr.strip()}')
        return proc.stdout.strip()

    def _render_decision_prompt(self, tweet: dict[str, Any], event: dict[str, Any], score: float) -> str:
        template = self.paths.decision_md.read_text(encoding='utf-8') if self.paths.decision_md.exists() else ''
        payload = {
            'task_name': self.cfg.get('TASK_NAME'),
            'max_asset_usd': self.cfg.get('MAX_ASSET_USD', 10),
            'trusted_media': self.cfg.get('TRUSTED_MEDIA', []),
            'rag_score_threshold': self.cfg.get('RAG_SCORE_THRESHOLD', 0.70),
            'match_score': score,
            'tweet': tweet,
            'event': {
                'event_id': event.get('event_id'),
                'slug': event.get('slug'),
                'title': event.get('title'),
                'description': event.get('description'),
                'child_options': event.get('child_options', []),
            },
        }
        return f"{template}\n\n# CONTEXT\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    def _ensure_trader(self) -> SimplePolymarketTrader:
        if self.trader is not None:
            return self.trader
        import os

        private_key = os.getenv('POLYMARKET_PRIVATE_KEY')
        if not private_key:
            raise RuntimeError('POLYMARKET_PRIVATE_KEY missing')
        self.trader = SimplePolymarketTrader(private_key)
        self.trader.initialize()
        return self.trader

    async def process_news(self, tweet: dict[str, Any]) -> None:
        threshold = float(self.cfg.get('RAG_SCORE_THRESHOLD', 0.70))
        matches = await asyncio.to_thread(self.rag.search, self.paths.vector_dir, tweet.get('text', ''), 5)
        matched = [m for m in matches if m.score >= threshold]

        log_row: dict[str, Any] = {
            'time': datetime.now(timezone.utc).isoformat(),
            'tweet': tweet,
            'threshold': threshold,
            'candidates': [{'score': m.score, 'event': m.event} for m in matches],
            'triggered': bool(matched),
        }

        if not matched:
            self._append_jsonl(self.paths.decision_records_jsonl, log_row)
            return

        best = matched[0]
        prompt = self._render_decision_prompt(tweet, best.event, best.score)
        log_row['prompt'] = prompt

        if not self.cfg.get('DECISION_ENABLED', True):
            log_row['decision'] = 'disabled'
            self._append_jsonl(self.paths.decision_records_jsonl, log_row)
            return

        response = await asyncio.to_thread(self._openclaw_call, prompt)
        log_row['openclaw_response'] = response

        action = parse_trade_action_from_openclaw(response, float(self.cfg.get('MAX_ASSET_USD', 10)))
        if action is None:
            log_row['trade'] = 'skip_invalid_json'
            self._append_jsonl(self.paths.decision_records_jsonl, log_row)
            return

        if not self.cfg.get('TRADING_ENABLED', True):
            log_row['trade'] = 'disabled'
            self._append_jsonl(self.paths.decision_records_jsonl, log_row)
            return

        trader = self._ensure_trader()
        if action.side == 'buy':
            result = await asyncio.to_thread(trader.market_buy, action.token_id, action.amount_usd)
        else:
            result = await asyncio.to_thread(trader.market_sell, action.token_id, action.amount_usd)

        log_row['trade'] = {'action': action.__dict__, 'result': result}
        self._append_jsonl(self.paths.trade_log_jsonl, {
            'time': datetime.now(timezone.utc).isoformat(),
            'task_name': self.task_name,
            'tweet': tweet,
            'action': action.__dict__,
            'result': result,
        })
        self._append_jsonl(self.paths.decision_records_jsonl, log_row)

    def _build_twitter_client(self):
        from twikit import Client

        auth = str(self.cfg.get('TWITTER_AUTH_TOKEN', '')).strip()
        ct0 = str(self.cfg.get('TWITTER_CT0', '')).strip()
        if not auth or not ct0:
            raise RuntimeError('Please set TWITTER_AUTH_TOKEN and TWITTER_CT0 in task_config.py')

        c = Client(language='en-US')
        c.set_cookies({'auth_token': auth, 'ct0': ct0})
        return c

    async def twitter_loop(self) -> None:
        c = self._build_twitter_client()
        watch_users = {str(x).strip() for x in self.cfg.get('WATCH_USERS', []) if str(x).strip()}
        if not watch_users:
            raise RuntimeError('WATCH_USERS is empty in task_config.py')

        last_seen = self._load_last_seen()
        poll_interval = int(self.cfg.get('TWITTER_POLL_INTERVAL_SECONDS', 60))

        while True:
            try:
                timeline = await c.get_latest_timeline()
                for tw in timeline:
                    user = tw.user.screen_name
                    if user not in watch_users:
                        continue
                    tid = str(tw.id)
                    prev = last_seen.get(user)
                    if prev is None:
                        last_seen[user] = tid
                        self._save_last_seen(last_seen)
                        continue
                    if int(tid) <= int(prev):
                        continue

                    tweet = {
                        'tweet_id': tid,
                        'user': user,
                        'text': tw.text,
                        'created_at': getattr(tw, 'created_at', None),
                        'url': f'https://x.com/{user}/status/{tid}',
                    }
                    self._append_jsonl(self.paths.tweet_jsonl, tweet)
                    await self.process_news(tweet)

                    last_seen[user] = tid
                    self._save_last_seen(last_seen)
            except Exception:
                logging.exception('twitter loop error')
                await asyncio.sleep(15)

            await asyncio.sleep(poll_interval)

    async def run_forever(self) -> None:
        task_text = self.paths.task_md.read_text(encoding='utf-8') if self.paths.task_md.exists() else ''
        logging.info('task.md loaded for %s: %s', self.task_name, task_text)

        await self.refresh_market_and_vectors()

        refresh_interval = int(self.cfg.get('MARKET_REFRESH_INTERVAL_SECONDS', 86400))

        async def refresh_loop() -> None:
            while True:
                await asyncio.sleep(refresh_interval)
                try:
                    await self.refresh_market_and_vectors()
                except Exception:
                    logging.exception('refresh loop error')

        await asyncio.gather(refresh_loop(), self.twitter_loop())
