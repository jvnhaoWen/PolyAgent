from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EventMatch:
    score: float
    event: dict[str, Any]


class EventRAG:
    def __init__(self, model_name: str = 'sentence-transformers/all-MiniLM-L6-v2') -> None:
        self.model_name = model_name
        self._model = None
        self._faiss = None

    def _init(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        import faiss

        self._model = SentenceTransformer(self.model_name)
        self._faiss = faiss

    def _build_market_document(self, event: dict[str, Any], market: dict[str, Any]) -> str:
        question = str(market.get('question', '')).strip()
        if not question:
            return ''

        market_desc = str(market.get('description', '')).strip()
        event_title = str(event.get('title', '')).strip()
        event_desc = str(event.get('description', '')).strip()

        parts = [question]
        if market_desc:
            parts.append(market_desc)
        if event_title and event_title != question:
            parts.append(event_title)
        if event_desc and event_desc != market_desc:
            parts.append(event_desc)
        return '\n'.join(parts)

    def _iter_market_candidates(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        child_options = event.get('child_options')
        if isinstance(child_options, list) and child_options:
            candidates = [opt for opt in child_options if str(opt.get('question', '')).strip()]
            if candidates:
                return candidates

        candidates: list[dict[str, Any]] = []
        for market in event.get('markets', []):
            try:
                volume = float(market.get('volume', 0) or 0)
            except Exception:
                continue
            if volume <= 0:
                continue
            if not str(market.get('question', '')).strip():
                continue
            candidates.append(market)

        if candidates:
            return candidates

        fallback_title = str(event.get('title', '')).strip()
        if not fallback_title:
            return []

        return [
            {
                'market_id': str(event.get('event_id', event.get('id', ''))),
                'question': fallback_title,
                'description': str(event.get('description', '')),
                'volume': float(event.get('volume', 0) or 0),
                'group_item_title': fallback_title,
            }
        ]

    def _build_event_payload(self, event: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload['matched_market'] = {
            'market_id': str(market.get('market_id', market.get('id', ''))),
            'question': str(market.get('question', '')),
            'description': str(market.get('description', event.get('description', ''))),
            'volume': float(market.get('volume', 0) or 0),
            'group_item_title': str(market.get('group_item_title', market.get('groupItemTitle', ''))),
        }
        return payload

    def build(self, events_jsonl: Path, out_dir: Path) -> int:
        self._init()
        assert self._model is not None
        assert self._faiss is not None

        records: list[dict[str, Any]] = []
        texts: list[str] = []
        with events_jsonl.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                for market in self._iter_market_candidates(event):
                    doc = self._build_market_document(event, market)
                    if not doc:
                        continue
                    records.append(self._build_event_payload(event, market))
                    texts.append(doc)

        out_dir.mkdir(parents=True, exist_ok=True)
        if not texts:
            (out_dir / 'events.json').write_text('[]', encoding='utf-8')
            return 0

        emb = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        index = self._faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)

        self._faiss.write_index(index, str(out_dir / 'events.faiss'))
        (out_dir / 'events.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        (out_dir / 'meta.json').write_text(
            json.dumps({'model_name': self.model_name, 'count': len(records)}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        return len(records)

    def search(self, vector_dir: Path, text: str, top_k: int = 5) -> list[EventMatch]:
        self._init()
        assert self._model is not None
        assert self._faiss is not None

        index_path = vector_dir / 'events.faiss'
        events_path = vector_dir / 'events.json'
        if not index_path.exists() or not events_path.exists():
            return []

        events = json.loads(events_path.read_text(encoding='utf-8'))
        if not events:
            return []

        index = self._faiss.read_index(str(index_path))
        q = self._model.encode([text], convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        scores, idxs = index.search(q, top_k)

        matches: list[EventMatch] = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0 or idx >= len(events):
                continue
            matches.append(EventMatch(score=float(score), event=events[idx]))
        return matches
