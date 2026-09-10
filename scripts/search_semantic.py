#!/usr/bin/env python3
"""
Semantic search using FAISS + multilingual embeddings.
Replaces old string-matching + dictionary approach.
"""

import json
import re
import numpy as np
from pathlib import Path

# Add scripts path for cache_manager
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".github" / "scripts"))

from cache_manager import get_cache_dir

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
    # Bei Kapitel-Filter wird NACH dem Top-k gefiltert: der Kandidatenpool muss
    # deshalb der ganze Index sein, sonst bleiben einzelne Laender leer (z.B. "CZ"
    # liefert nichts, weil DE/AT die Top-Treffer belegen). IndexFlatIP scannt
    # ohnehin alle Vektoren, das kostet also nur die Rueckgabe groesserer Listen.
    k = index.ntotal if chapters else min(max_results * 3, index.ntotal)
    scores, indices = index.search(query_vec, k)

    # Collect results with chapter filtering
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        chunk = chunks[idx]
        source = chunk.get("source", "")

        # Apply chapter filter
        if chapters and not _match_chapter(chunk, chapters):
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


def _match_chapter(chunk: dict, chapters: list[str]) -> bool:
    """Kapitel-Filter fuer einen Chunk.

    Drei Wege, weil Volt-Dokumentnamen uneinheitlich sind:
      1. Domain der Dokument-URL passt zur Kapitel-Website (zuverlaessigster Weg)
      2. vollstaendiger Kapitelname im Quellnamen ("Volt Tschechien Politiky")
      3. Laendercode als eigenstaendiges Wort ("Volt HR Policy") - NICHT als
         Teilstring, sonst matcht "LV" in "digitaLV ersion" oder "SE" in "hessen".
    """
    if not chapters:
        return True

    # Load chapters config for country code matching
    chapters_path = Path(__file__).parent / "chapters.json"
    chapter_config = {}
    if chapters_path.exists():
        with open(chapters_path, 'r', encoding='utf-8') as f:
            chapter_config = json.load(f).get("chapters", {})

    source_lower = str(chunk.get("source", "")).lower()
    url_lower = str(chunk.get("url", "")).lower()

    for chapter in chapters:
        chapter_lower = chapter.lower().strip()
        if chapter_lower in ("eu", "europa", "volt europa"):
            if ("volteuropa.org" in url_lower or "volt europa" in source_lower
                    or "europa" in source_lower
                    or re.search(r"(?<![a-z0-9])eu(?![a-z0-9])", source_lower)):
                return True
            continue
        for name, info in chapter_config.items():
            if info.get("country", "").lower() != chapter_lower:
                continue
            # Domain ohne www, damit www./nicht-www-Varianten beide passen
            domain = info.get("website", "").split("//")[-1].rstrip("/").lower()
            domain = domain[4:] if domain.startswith("www.") else domain
            if domain and domain in url_lower:
                return True
            if name.lower() in source_lower:
                return True
            if re.search(rf"(?<![a-z0-9]){re.escape(chapter_lower)}(?![a-z0-9])", source_lower):
                return True
    return False
