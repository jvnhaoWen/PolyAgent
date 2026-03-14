from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass(slots=True)
class MarketConfig:
    tag_slug: str
    volume_min: int
    events_jsonl: Path
    filtered_events_jsonl: Path
    limit: int = 100
    max_retries: int = 3
    max_empty_fetches: int = 3


class MarketPipeline:
    def __init__(self, cfg: MarketConfig) -> None:
        self.cfg = cfg

    @property
    def base_url(self) -> str:
        return f'https://gamma-api.polymarket.com/events?tag_slug={self.cfg.tag_slug}&volume_min={self.cfg.volume_min}'

    def _fetch_page(self, session: requests.Session, params: dict[str, Any], attempt: int = 0):
        try:
            resp = session.get(self.base_url, params=params, timeout=30)
            if resp.status_code == 429:
                if attempt >= self.cfg.max_retries:
                    return None
                time.sleep(60)
                return self._fetch_page(session, params, attempt + 1)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt >= self.cfg.max_retries - 1:
                return None
            time.sleep(5)
            return self._fetch_page(session, params, attempt + 1)

    def scrape_events(self) -> int:
        self.cfg.events_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.events_jsonl.write_text('', encoding='utf-8')

        offset = 0
        empty_count = 0
        previous_text = None
        total = 0

        session = requests.Session()
        session.headers.update({'User-Agent': 'PolyMonitor/1.0'})

        while True:
            resp = self._fetch_page(session, {'limit': self.cfg.limit, 'offset': offset})
            if resp is None:
                break

            if previous_text == resp.text:
                break
            previous_text = resp.text

            try:
                data = resp.json()
                events = data if isinstance(data, list) else []
            except Exception:
                events = []

            if not events:
                empty_count += 1
                if empty_count >= self.cfg.max_empty_fetches:
                    break
            else:
                empty_count = 0

            with self.cfg.events_jsonl.open('a', encoding='utf-8') as f:
                for e in events:
                    f.write(json.dumps(e, ensure_ascii=False) + '\n')
                    total += 1

            offset += self.cfg.limit
            time.sleep(0.5)

        return total

    def filter_active_events(self) -> int:
        self.cfg.filtered_events_jsonl.parent.mkdir(parents=True, exist_ok=True)
        count = 0

        with self.cfg.events_jsonl.open('r', encoding='utf-8') as fin, self.cfg.filtered_events_jsonl.open('w', encoding='utf-8') as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                child_options = []

                for market in event.get('markets', []):
                    if str(market.get('acceptingOrders', '')).lower() != 'true':
                        continue
                    try:
                        if float(market.get('volume', 0) or 0) <= 0:
                            continue
                    except Exception:
                        continue

                    raw_token_ids = market.get('clobTokenIds', [])
                    if isinstance(raw_token_ids, str):
                        try:
                            token_ids = json.loads(raw_token_ids)
                        except Exception:
                            token_ids = []
                    else:
                        token_ids = raw_token_ids

                    if len(token_ids) < 2:
                        continue

                    child_options.append(
                        {
                            'market_id': str(market.get('id', '')),
                            'group_item_title': str(market.get('groupItemTitle', '')),
                            'question': str(market.get('question', '')),
                            'token_yes': str(token_ids[0]),
                            'token_no': str(token_ids[1]),
                            'volume': float(market.get('volume', 0) or 0),
                        }
                    )

                if not child_options:
                    continue

                output = {
                    'event_id': str(event.get('id', '')),
                    'slug': str(event.get('slug', '')),
                    'title': str(event.get('title', '')),
                    'description': str(event.get('description', '')),
                    'volume': float(event.get('volume', 0) or 0),
                    'child_options': sorted(child_options, key=lambda x: float(x.get('volume', 0)), reverse=True),
                }
                fout.write(json.dumps(output, ensure_ascii=False) + '\n')
                count += 1

        return count
