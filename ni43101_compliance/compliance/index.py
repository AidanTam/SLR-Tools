"""Chunk the report, embed it, and retrieve the most relevant chunks per criterion.

Chunks are built per page so page citations stay exact. Embeddings are cached to
disk keyed on the report + model + chunk params, so re-running with a different
checklist skips the expensive re-embedding.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

from .llm import OllamaClient
from .models import Chunk, Page


class ReportIndex:
    def __init__(self, chunks: List[Chunk], matrix: np.ndarray):
        self.chunks = chunks
        # L2-normalize once so cosine similarity is a plain dot product.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.matrix = matrix / norms

    def retrieve(
        self,
        query_vec: List[float],
        top_k: int = 6,
        item_id: str = "",
        item_boost: float = 0.15,
        max_chars: int = 6500,
    ) -> List[Chunk]:
        q = np.asarray(query_vec, dtype=np.float32)
        nq = np.linalg.norm(q)
        if nq:
            q = q / nq
        scores = self.matrix @ q  # cosine similarity

        if item_id:
            boost = np.array(
                [item_boost if c.item_id == item_id else 0.0 for c in self.chunks],
                dtype=np.float32,
            )
            scores = scores + boost

        order = np.argsort(-scores)
        picked: List[Chunk] = []
        used = 0
        for idx in order:
            if len(picked) >= top_k:
                break
            chunk = self.chunks[idx]
            if used + len(chunk.text) > max_chars and picked:
                continue
            picked.append(chunk)
            used += len(chunk.text)
        return picked


def build_chunks(
    pages: List[Page],
    page_items: Dict[int, Tuple[str, str]],
    chunk_size: int,
    overlap: int,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        item_id, item_title = page_items.get(page.number, ("", ""))
        step = max(chunk_size - overlap, 1)
        for start in range(0, len(text), step):
            piece = text[start : start + chunk_size].strip()
            if len(piece) < 40:
                continue
            chunks.append(
                Chunk(text=piece, page=page.number, item_id=item_id, item_title=item_title)
            )
            if start + chunk_size >= len(text):
                break
    return chunks


def build_index(
    pages: List[Page],
    page_items: Dict[int, Tuple[str, str]],
    llm: OllamaClient,
    chunk_size: int,
    overlap: int,
    cache_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> ReportIndex:
    chunks = build_chunks(pages, page_items, chunk_size, overlap)
    if not chunks:
        raise ValueError("No extractable text found in the report.")

    cache_path = None
    if cache_key and cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{cache_key}.npz")
        if os.path.exists(cache_path):
            cached = _load_cache(cache_path)
            if cached is not None and len(cached[0]) == len(chunks):
                return ReportIndex(cached[0], cached[1])

    vectors = []
    for chunk in tqdm(chunks, desc="Embedding report", unit="chunk"):
        vectors.append(llm.embed(chunk.text))
    matrix = np.asarray(vectors, dtype=np.float32)

    if cache_path:
        _save_cache(cache_path, chunks, matrix)
    return ReportIndex(chunks, matrix)


def report_cache_key(report_path: str, embed_model: str, chunk_size: int, overlap: int) -> str:
    h = hashlib.sha256()
    with open(report_path, "rb") as fh:
        h.update(fh.read())
    h.update(f"{embed_model}:{chunk_size}:{overlap}".encode())
    return h.hexdigest()[:16]


def _save_cache(path: str, chunks: List[Chunk], matrix: np.ndarray) -> None:
    meta = [
        {"text": c.text, "page": c.page, "item_id": c.item_id, "item_title": c.item_title}
        for c in chunks
    ]
    np.savez_compressed(path, matrix=matrix, meta=json.dumps(meta))


def _load_cache(path: str) -> Optional[Tuple[List[Chunk], np.ndarray]]:
    try:
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data["meta"]))
        chunks = [
            Chunk(text=m["text"], page=m["page"], item_id=m["item_id"], item_title=m["item_title"])
            for m in meta
        ]
        return chunks, data["matrix"].astype(np.float32)
    except Exception:
        return None
