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

    def build(self, events_jsonl: Path, out_dir: Path) -> int:
        self._init()
        assert self._model is not None
        assert self._faiss is not None

        events: list[dict[str, Any]] = []
        texts: list[str] = []
        with events_jsonl.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                title = str(ev.get('title', ''))
                desc = str(ev.get('description', ''))
                if not (title or desc):
                    continue
                events.append(ev)
                texts.append(f'{title}. {desc}')

        out_dir.mkdir(parents=True, exist_ok=True)
        if not texts:
            (out_dir / 'events.json').write_text('[]', encoding='utf-8')
            return 0

        emb = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        index = self._faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)

        self._faiss.write_index(index, str(out_dir / 'events.faiss'))
        (out_dir / 'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
        (out_dir / 'meta.json').write_text(
            json.dumps({'model_name': self.model_name, 'count': len(events)}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        return len(events)

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
