from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass(slots=True)
class MarketRefreshConfig:
    tag_slug: str
    volume_min: int
    output_events_jsonl: Path
    output_extracted_jsonl: Path
    limit: int = 100
    max_retries: int = 3
    max_empty_fetches: int = 3


class MarketDataBuilder:
    def __init__(self, cfg: MarketRefreshConfig) -> None:
        self.cfg = cfg

    @property
    def base_url(self) -> str:
        return f"https://gamma-api.polymarket.com/events?tag_slug={self.cfg.tag_slug}&volume_min={self.cfg.volume_min}"

    def _fetch_page(self, session: requests.Session, params: dict[str, Any], attempt: int = 0):
        try:
            response = session.get(self.base_url, params=params, timeout=30)
            if response.status_code == 429:
                time.sleep(60)
                if attempt < self.cfg.max_retries:
                    return self._fetch_page(session, params, attempt + 1)
                return None

            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt < self.cfg.max_retries - 1:
                time.sleep(5)
                return self._fetch_page(session, params, attempt + 1)
            return None

    def scrape_all_markets(self) -> int:
        self.cfg.output_events_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.output_events_jsonl.write_text('', encoding='utf-8')

        current_offset = 0
        empty_fetch_count = 0
        previous_response_text = None
        total_markets_written = 0

        session = requests.Session()
        session.headers.update({'User-Agent': 'Polymarket Scraper Bot (Python/Requests)'})

        while True:
            params = {'limit': self.cfg.limit, 'offset': current_offset}
            response = self._fetch_page(session, params)
            if response is None:
                break

            current_response_text = response.text
            if current_response_text == previous_response_text:
                break
            previous_response_text = current_response_text

            try:
                data = response.json()
                fetched_markets = data if isinstance(data, list) else []
            except Exception:
                fetched_markets = []

            if not fetched_markets:
                empty_fetch_count += 1
                if empty_fetch_count >= self.cfg.max_empty_fetches:
                    break
            else:
                empty_fetch_count = 0

            with self.cfg.output_events_jsonl.open('a', encoding='utf-8') as f:
                for event in fetched_markets:
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')
                    total_markets_written += 1

            current_offset += self.cfg.limit
            time.sleep(0.5)

        return total_markets_written

    def extract_active_markets(self) -> int:
        seen: set[tuple[str, str, str]] = set()
        count = 0
        self.cfg.output_extracted_jsonl.parent.mkdir(parents=True, exist_ok=True)

        with self.cfg.output_events_jsonl.open('r', encoding='utf-8') as fin, self.cfg.output_extracted_jsonl.open(
            'w', encoding='utf-8'
        ) as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                event_description = event.get('description', '')

                for market in event.get('markets', []):
                    accepting = str(market.get('acceptingOrders', '')).lower()
                    if accepting != 'true':
                        continue

                    try:
                        if float(market.get('volume', '0')) == 0:
                            continue
                    except Exception:
                        continue

                    token_ids_str = market.get('clobTokenIds', '[]')
                    try:
                        token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str
                    except Exception:
                        token_ids = []

                    if len(token_ids) < 2:
                        continue

                    slug = market.get('slug', '')
                    key = (slug, str(token_ids[0]), str(token_ids[1]))
                    if key in seen:
                        continue
                    seen.add(key)

                    result = {
                        'event_id': str(event.get('id', '')),
                        'event_title': event.get('title', ''),
                        'event_description': event_description,
                        'slug': slug,
                        'question': market.get('question', ''),
                        'description': market.get('description', event_description),
                        'token_yes': str(token_ids[0]),
                        'token_no': str(token_ids[1]),
                        'volume': float(market.get('volume', 0) or 0),
                    }
                    fout.write(json.dumps(result, ensure_ascii=False) + '\n')
                    count += 1

        return count
