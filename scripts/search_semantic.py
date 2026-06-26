#!/usr/bin/env python3
"""
Semantic search using FAISS + multilingual embeddings.
Replaces old string-matching + dictionary approach.
"""

import json
import os
import numpy as np
from pathlib import Path

# Add scripts path for cache_manager
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".github" / "scripts"))

from cache_manager import get_cache_dir

# Allow override via env var (production: HF Space setzt VOLT_CACHE_DIR)
_env_cache = os.environ.get("VOLT_CACHE_DIR")
if _env_cache:
    _cache_path = Path(_env_cache)
    _cache_path.mkdir(parents=True, exist_ok=True)
    CACHE_DIR = _cache_path
else:
    CACHE_DIR = get_cache_dir()
INDEX_PATH = CACHE_DIR / "faiss.index"
CHUNKS_PATH = CACHE_DIR / "chunks.json"

_model = None


def _load_model():
    """Lazy-load embedding model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(
            "intfloat/multilingual-e5-small",
            trust_remote_code=True,
        )
    return _model


def _load_index():
    """Load FAISS index and chunks."""
    if not INDEX_PATH.exists() or not CHUNKS_PATH.exists():
        return None, []

    import faiss
    index = faiss.read_index(str(INDEX_PATH))
    with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    return index, chunks


def index_available() -> bool:
    """Check if a built index exists."""
    return INDEX_PATH.exists() and CHUNKS_PATH.exists()


def semantic_search(query: str, max_results: int = 10, chapters: list[str] = None) -> list:
    """Search using FAISS cosine similarity.
    
    Args:
        query: Search term in any language
        max_results: Max results to return
        chapters: Optional filter — list of country codes (DE, FR, IT, ...) or chapter names
    
    Returns:
        List of result dicts with text, url, date, source, score
    """
    index, chunks = _load_index()
    if index is None:
        return [{"error": "No index found. Run build_index.py first."}]

    model = _load_model()

    # Embed query
    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    # Search
    scores, indices = index.search(query_vec, min(max_results * 3, index.ntotal))

    # Collect results with chapter filtering
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        chunk = chunks[idx]
        source = chunk.get("source", "")

        # Apply chapter filter
        if chapters and not _match_chapter(source, chapters):
            continue

        results.append({
            "title": chunk.get("title", ""),
            "url": chunk.get("url", ""),
            "date": chunk.get("date", ""),
            "source": source,
            "type": chunk.get("type", "news"),
            "text_preview": chunk.get("text", "")[:500],
            "score": round(float(score), 4),
        })

        if len(results) >= max_results:
            break

    return results


def _match_chapter(source: str, chapters: list[str]) -> bool:
    """Check if a source matches the requested chapter filter."""
    if not chapters:
        return True

    # Load chapters config for country code matching
    chapters_path = Path(__file__).parent / "chapters.json"
    chapter_config = {}
    if chapters_path.exists():
        with open(chapters_path, 'r', encoding='utf-8') as f:
            chapter_config = json.load(f).get("chapters", {})

    source_lower = source.lower()
    for chapter in chapters:
        chapter_lower = chapter.lower().strip()
        if chapter_lower in ("eu", "europa", "volt europa"):
            if "volt europa" in source_lower or "europa" in source_lower:
                return True
            continue
        if chapter_lower in source_lower or source_lower in chapter_lower:
            return True
        # Match country codes
        for name, info in chapter_config.items():
            if info.get("country", "").lower() == chapter_lower:
                if name.lower() in source_lower or source_lower in name.lower():
                    return True
    return False
