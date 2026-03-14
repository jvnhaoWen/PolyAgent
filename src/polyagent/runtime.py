from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .market import MarketDataBuilder, MarketRefreshConfig
from .rag import EventRAG
from .tasking import load_task_config
from .trading import SimplePolymarketTrader, parse_trade_action_from_openclaw


@dataclass(slots=True)
class RuntimeContext:
    task_name: str
    task_dir: Path
    cfg: dict[str, Any]


class PolyMonitorRuntime:
    def __init__(self, task_name: str) -> None:
        task_dir = Path('tasks') / task_name
        cfg = load_task_config(task_dir)
        self.ctx = RuntimeContext(task_name=task_name, task_dir=task_dir, cfg=cfg)

        self.events_jsonl = task_dir / 'data' / 'events.jsonl'
        self.extracted_jsonl = task_dir / 'data' / 'extracted_markets.jsonl'
        self.vector_dir = task_dir / 'vector'
        self.tweet_jsonl = task_dir / 'data' / 'tweets.jsonl'
        self.last_seen_path = task_dir / 'data' / 'last_seen.json'
        self.test_records = task_dir / 'test' / 'decision_records.jsonl'
        self.trade_log = task_dir / 'logs' / 'trades.jsonl'

        self.rag = EventRAG('sentence-transformers/all-MiniLM-L6-v2')
        self.trader: SimplePolymarketTrader | None = None

    def _load_last_seen(self) -> dict[str, str]:
        if not self.last_seen_path.exists():
            return {}
        try:
            return json.loads(self.last_seen_path.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_last_seen(self, data: dict[str, str]) -> None:
        self.last_seen_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def refresh_markets_and_vectors(self) -> None:
        mcfg = MarketRefreshConfig(
            tag_slug=str(self.ctx.cfg.get('TOPIC_TAG_SLUG', 'iran')),
            volume_min=int(self.ctx.cfg.get('VOLUME_MIN', 1_000_000)),
            output_events_jsonl=self.events_jsonl,
            output_extracted_jsonl=self.extracted_jsonl,
        )
        builder = MarketDataBuilder(mcfg)

        events_written = await asyncio.to_thread(builder.scrape_all_markets)
        extracted = await asyncio.to_thread(builder.extract_active_markets)
        if extracted == 0:
            logging.warning('There is no matched market for your key words currently.')

        indexed = await asyncio.to_thread(self.rag.build_index, self.extracted_jsonl, self.vector_dir)
        logging.info('market refresh finished: events=%s extracted=%s indexed=%s', events_written, extracted, indexed)

    def _build_twitter_client(self):
        from twikit import Client
        language = 'en-US'
        user_agent = (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/122 Safari/537.36'
        )
        client = Client(language=language, user_agent=user_agent)

        auth_token = self.ctx.cfg.get('TWITTER_AUTH_TOKEN')
        ct0 = self.ctx.cfg.get('TWITTER_CT0')
        if not auth_token or not ct0:
            raise RuntimeError('missing TWITTER_AUTH_TOKEN/TWITTER_CT0 in task_config.py')

        client.set_cookies({'auth_token': auth_token, 'ct0': ct0})
        return client

    def _render_prompt(self, tweet: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
        c = candidates[0]
        record = c['record']
        trusted_media = self.ctx.cfg.get('TRUSTED_MEDIA', [])
        return (
            'You are OpenClaw trading agent. Decide whether to trade now.\\n'
            f"Task={self.ctx.cfg.get('TASK_NAME')}\\n"
            f"MAX_ASSET_USD={self.ctx.cfg.get('MAX_ASSET_USD', 10)}\\n"
            f"Trusted media={trusted_media}\\n\\n"
            f"Tweet={json.dumps(tweet, ensure_ascii=False)}\\n"
            f"Top market score={c['score']}\\n"
            f"Market event={record.get('event_title')}\\n"
            f"Question={record.get('question')}\\n"
            f"Description={record.get('description')}\\n"
            f"Token yes={record.get('token_yes')} token no={record.get('token_no')}\\n\\n"
            'Return STRICT JSON: {"should_trade": bool, "side": "buy|sell", "token_id": "...", "amount_usd": number, "reason": "..."}'
        )

    def _call_openclaw(self, prompt: str) -> str:
        command = self.ctx.cfg.get('OPENCLAW_COMMAND', ['openclaw', 'agent', '--message'])
        if not isinstance(command, list) or not command:
            raise ValueError('OPENCLAW_COMMAND must be a non-empty list')
        proc = subprocess.run(command + [prompt], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f'openclaw call failed: {proc.stderr.strip()}')
        return proc.stdout.strip()

    def _ensure_trader(self) -> SimplePolymarketTrader:
        if self.trader is not None:
            return self.trader

        import os

        private_key = os.getenv('POLYMARKET_PRIVATE_KEY')
        if not private_key:
            raise RuntimeError('POLYMARKET_PRIVATE_KEY missing in environment')

        self.trader = SimplePolymarketTrader(private_key)
        self.trader.initialize()
        return self.trader

    async def _handle_tweet(self, tweet: dict[str, Any]) -> None:
        text = tweet.get('text', '')
        top_k = int(self.ctx.cfg.get('RAG_TOP_K', 5))
        threshold = float(self.ctx.cfg.get('RAG_SCORE_THRESHOLD', 0.70))

        matches = await asyncio.to_thread(self.rag.search, self.vector_dir, text, top_k)
        filtered = [m for m in matches if m.score >= threshold]

        record_for_test: dict[str, Any] = {
            'time': datetime.now(timezone.utc).isoformat(),
            'tweet': tweet,
            'threshold': threshold,
            'candidates': [{'score': m.score, 'record': m.record} for m in matches],
            'matched': bool(filtered),
        }

        if not filtered:
            self._append_jsonl(self.test_records, record_for_test)
            return

        if not self.ctx.cfg.get('DECISION_ENABLED', True):
            record_for_test['decision'] = 'disabled'
            self._append_jsonl(self.test_records, record_for_test)
            return

        prompt = self._render_prompt(tweet, [{'score': filtered[0].score, 'record': filtered[0].record}])
        llm_resp = await asyncio.to_thread(self._call_openclaw, prompt)
        record_for_test['prompt'] = prompt
        record_for_test['openclaw_response'] = llm_resp

        action = parse_trade_action_from_openclaw(llm_resp, float(self.ctx.cfg.get('MAX_ASSET_USD', 10)))
        if action is None:
            record_for_test['trade'] = 'skip_invalid_response'
            self._append_jsonl(self.test_records, record_for_test)
            return

        if not self.ctx.cfg.get('TRADING_ENABLED', True):
            record_for_test['trade'] = 'disabled'
            self._append_jsonl(self.test_records, record_for_test)
            return

        trader = self._ensure_trader()
        if action.side == 'buy':
            trade_result = await asyncio.to_thread(trader.market_buy, action.token_id, action.amount_usd)
        else:
            trade_result = await asyncio.to_thread(trader.market_sell, action.token_id, action.amount_usd)

        record_for_test['trade'] = {'action': action.__dict__, 'result': trade_result}
        self._append_jsonl(self.trade_log, {
            'time': datetime.now(timezone.utc).isoformat(),
            'tweet': tweet,
            'action': action.__dict__,
            'result': trade_result,
        })
        self._append_jsonl(self.test_records, record_for_test)

    async def run_twitter_loop(self) -> None:
        client = self._build_twitter_client()
        watch_users = {str(x) for x in self.ctx.cfg.get('WATCH_USERS', []) if str(x).strip()}
        if not watch_users:
            raise RuntimeError('WATCH_USERS is empty')

        last_seen = self._load_last_seen()
        poll_interval = int(self.ctx.cfg.get('TWITTER_POLL_INTERVAL_SECONDS', 60))

        while True:
            try:
                timeline = await client.get_latest_timeline()
                for tw in timeline:
                    user = tw.user.screen_name
                    if user not in watch_users:
                        continue

                    tweet_id = str(tw.id)
                    prev = last_seen.get(user)
                    if prev is None:
                        last_seen[user] = tweet_id
                        self._save_last_seen(last_seen)
                        continue
                    if int(tweet_id) <= int(prev):
                        continue

                    rec = {
                        'tweet_id': tweet_id,
                        'user': user,
                        'text': tw.text,
                        'created_at': getattr(tw, 'created_at', None),
                        'url': f'https://x.com/{user}/status/{tweet_id}',
                    }
                    self._append_jsonl(self.tweet_jsonl, rec)
                    await self._handle_tweet(rec)
                    last_seen[user] = tweet_id
                    self._save_last_seen(last_seen)
            except Exception:
                logging.exception('twitter loop error')
                await asyncio.sleep(15)

            await asyncio.sleep(poll_interval)

    async def run_forever(self) -> None:
        task_md = (self.ctx.task_dir / 'task.md').read_text(encoding='utf-8')
        logging.info('Loaded task.md for %s:\n%s', self.ctx.task_name, task_md[:500])

        await self.refresh_markets_and_vectors()

        refresh_interval = int(self.ctx.cfg.get('MARKET_REFRESH_INTERVAL_SECONDS', 86400))

        async def refresh_loop() -> None:
            while True:
                await asyncio.sleep(refresh_interval)
                try:
                    await self.refresh_markets_and_vectors()
                except Exception:
                    logging.exception('refresh loop failed')

        await asyncio.gather(refresh_loop(), self.run_twitter_loop())
