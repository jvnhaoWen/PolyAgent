from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MatchCandidate:
    score: float
    record: dict[str, Any]


class EventRAG:
    def __init__(self, model_name: str = 'sentence-transformers/all-MiniLM-L6-v2') -> None:
        self.model_name = model_name
        self.model = None
        self.faiss = None

    def _lazy_init(self) -> None:
        if self.model is not None and self.faiss is not None:
            return
        from sentence_transformers import SentenceTransformer
        import faiss

        self.model = SentenceTransformer(self.model_name)
        self.faiss = faiss

    def build_index(self, source_jsonl: Path, index_dir: Path) -> int:
        self._lazy_init()
        assert self.model is not None
        assert self.faiss is not None

        records: list[dict[str, Any]] = []
        texts: list[str] = []

        with source_jsonl.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                text = f"{r.get('event_title', '')}. {r.get('event_description', '')}. {r.get('question', '')}".strip()
                if not text:
                    continue
                records.append(r)
                texts.append(text)

        if not texts:
            index_dir.mkdir(parents=True, exist_ok=True)
            (index_dir / 'records.json').write_text('[]', encoding='utf-8')
            return 0

        emb = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        index = self.faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)

        index_dir.mkdir(parents=True, exist_ok=True)
        self.faiss.write_index(index, str(index_dir / 'events.faiss'))
        (index_dir / 'records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        (index_dir / 'meta.json').write_text(
            json.dumps({'model_name': self.model_name, 'count': len(records)}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        return len(records)

    def search(self, index_dir: Path, query: str, top_k: int = 5) -> list[MatchCandidate]:
        self._lazy_init()
        assert self.model is not None
        assert self.faiss is not None

        index_path = index_dir / 'events.faiss'
        records_path = index_dir / 'records.json'
        if not index_path.exists() or not records_path.exists():
            return []

        index = self.faiss.read_index(str(index_path))
        records = json.loads(records_path.read_text(encoding='utf-8'))
        if not records:
            return []

        emb = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True).astype('float32')
        scores, indices = index.search(emb, top_k)

        output: list[MatchCandidate] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(records):
                continue
            output.append(MatchCandidate(score=float(score), record=records[idx]))
        return output
