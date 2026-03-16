from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .decision import run_decision
from .market import MarketConfig, MarketPipeline
from .rag import EventRAG
from .tasking import load_task_config


@dataclass(slots=True)
class TaskRuntimePaths:
    task_dir: Path
    events_jsonl: Path
    filtered_events_jsonl: Path
    tweet_jsonl: Path
    last_seen_json: Path
    vector_dir: Path
    decision_records_jsonl: Path
    runtime_log_jsonl: Path
    decision_md: Path


class PolyMonitorRuntime:
    def __init__(self, task_name: str) -> None:
        task_dir = Path('tasks') / task_name
        self.task_name = task_name
        self.cfg = load_task_config(task_dir)

        self.paths = TaskRuntimePaths(
            task_dir=task_dir,
            events_jsonl=task_dir / 'data' / 'events.jsonl',
            filtered_events_jsonl=task_dir / 'data' / 'filtered_acceptingOrders.jsonl',
            tweet_jsonl=task_dir / 'data' / 'tweets.jsonl',
            last_seen_json=task_dir / 'data' / 'last_seen.json',
            vector_dir=task_dir / 'vector',
            decision_records_jsonl=task_dir / 'test' / 'decision_records.jsonl',
            runtime_log_jsonl=task_dir / 'logs' / 'runtime_events.jsonl',
            decision_md=task_dir / 'decision.md',
        )
        self.rag = EventRAG('sentence-transformers/all-MiniLM-L6-v2')

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
        self.cfg = load_task_config(self.paths.task_dir)

        pipeline = MarketPipeline(
            MarketConfig(
                tag_slug=str(self.cfg.get('TOPIC_TAG_SLUG', 'iran')),
                volume_min=int(self.cfg.get('VOLUME_MIN', 1_000_000)),
                events_jsonl=self.paths.events_jsonl,
                filtered_events_jsonl=self.paths.filtered_events_jsonl,
            )
        )
        events_count = await asyncio.to_thread(pipeline.scrape_events)
        filtered_count = await asyncio.to_thread(pipeline.filter_active_events)
        if filtered_count == 0:
            logging.warning('There is no matched market for your key words currently.')

        indexed = await asyncio.to_thread(self.rag.build, self.paths.filtered_events_jsonl, self.paths.vector_dir)
        logging.info('market refresh done events=%s filtered=%s indexed=%s', events_count, filtered_count, indexed)

    async def process_news(self, tweet: dict[str, Any]) -> None:
        self.cfg = load_task_config(self.paths.task_dir)

        logging.info('NEWS: user=%s tweet_id=%s text=%s', tweet.get('user'), tweet.get('tweet_id'), tweet.get('text'))
        self._append_jsonl(
            self.paths.runtime_log_jsonl,
            {
                'time': datetime.now(timezone.utc).isoformat(),
                'type': 'news',
                'tweet': tweet,
            },
        )

        threshold = float(self.cfg.get('RAG_SCORE_THRESHOLD', 0.70))
        matches = await asyncio.to_thread(self.rag.search, self.paths.vector_dir, tweet.get('text', ''), 5)
        matched = [m for m in matches if m.score >= threshold]

        row: dict[str, Any] = {
            'time': datetime.now(timezone.utc).isoformat(),
            'tweet': tweet,
            'threshold': threshold,
            'candidates': [{'score': m.score, 'event': m.event} for m in matches],
            'triggered': bool(matched),
        }

        if not matched:
            self._append_jsonl(self.paths.decision_records_jsonl, row)
            return

        if not self.cfg.get('DECISION_ENABLED', True):
            row['decision'] = 'disabled'
            self._append_jsonl(self.paths.decision_records_jsonl, row)
            return

        best = matched[0]
        template_text = self.paths.decision_md.read_text(encoding='utf-8') if self.paths.decision_md.exists() else None

        result = await asyncio.to_thread(
            run_decision,
            tweet,
            best.event,
            float(self.cfg.get('MIN_TRADE_USDC', 5)),
            float(self.cfg.get('MAX_TRADE_USDC', self.cfg.get('MAX_ASSET_USD', 10))),
            template_text,
            self.cfg.get('OPENCLAW_COMMAND', ['openclaw', 'agent', '--message']),
        )

        decision_summary = {
            'triggered': True,
            'event_id': best.event.get('event_id'),
            'event_title': best.event.get('title'),
            'score': best.score,
            'openclaw_response': result.response,
        }
        logging.info('DECISION: %s', json.dumps(decision_summary, ensure_ascii=False))
        self._append_jsonl(
            self.paths.runtime_log_jsonl,
            {
                'time': datetime.now(timezone.utc).isoformat(),
                'type': 'decision',
                **decision_summary,
            },
        )

        row['prompt'] = result.prompt
        row['openclaw_response'] = result.response
        row['trading_enabled'] = self.cfg.get('TRADING_ENABLED', True)
        self._append_jsonl(self.paths.decision_records_jsonl, row)

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
        self.cfg = load_task_config(self.paths.task_dir)
        c = self._build_twitter_client()
        watch_users = {str(x).strip() for x in self.cfg.get('WATCH_USERS', []) if str(x).strip()}
        if not watch_users:
            raise RuntimeError('WATCH_USERS is empty in task_config.py')

        last_seen = self._load_last_seen()
        poll_interval = int(self.cfg.get('TWITTER_POLL_INTERVAL_SECONDS', 60))

        while True:
            self.cfg = load_task_config(self.paths.task_dir)
            watch_users = {str(x).strip() for x in self.cfg.get('WATCH_USERS', []) if str(x).strip()}
            poll_interval = int(self.cfg.get('TWITTER_POLL_INTERVAL_SECONDS', 60))
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
        await self.refresh_market_and_vectors()

        async def refresh_loop() -> None:
            while True:
                self.cfg = load_task_config(self.paths.task_dir)
                refresh_interval_local = int(self.cfg.get('MARKET_REFRESH_INTERVAL_SECONDS', 86400))
                await asyncio.sleep(refresh_interval_local)
                try:
                    await self.refresh_market_and_vectors()
                except Exception:
                    logging.exception('refresh loop error')

        await asyncio.gather(refresh_loop(), self.twitter_loop())
