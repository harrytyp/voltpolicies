#!/usr/bin/env python3
"""
Build FAISS semantic index for Volt news + policies.
Uses multilingual sentence-transformers for cross-lingual search.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".github" / "scripts"))
from cache_manager import get_cache_dir

CACHE_DIR = get_cache_dir()
INDEX_PATH = CACHE_DIR / "faiss.index"
CHUNKS_PATH = CACHE_DIR / "chunks.json"
MODEL_NAME = "intfloat/multilingual-e5-small"


def load_news_chunks() -> list[dict]:
    """Load all news articles and split into searchable chunks."""
    chunks = []
    for nf in sorted(CACHE_DIR.glob("news_*.json")):
        source_name = nf.stem.replace("news_", "").replace("_", " ").replace("  ", " ").strip()
        try:
            with open(nf, 'r', encoding='utf-8') as f:
                articles = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        for article in articles:
            title = (article.get("title", "") or "").strip()
            desc = (article.get("description", "") or "").strip()
            text = f"{title}\n{desc}" if title and desc else (title or desc)
            if not text or len(text) < 20:
                continue
            
            # Skip noise: very short blurbs with no real content
            if len(text) < 60 and not re.search(r'[A-Za-z]{4,}', text):
                continue

            chunks.append({
                "text": text[:2000],
                "title": title,
                "url": article.get("link", ""),
                "date": article.get("date", ""),
                "source": source_name,
                "type": "news",
                "via": article.get("via", "rss"),
            })
    return chunks


def load_pdf_chunks() -> list[dict]:
    """Load PDF texts and split into page-level chunks.
    Skips admin/audit documents (ANBI, DPO, reports, etc.) that add noise.
    """
    admin_keywords = ['anbi', 'data protection report', 'dpo report', 'audit report', 
                      'audit opinion', 'privacy statement', 'officials handbook',
                      'integrity syllabus', 'vorlaufiger wahlwerbungsbericht',
                      'chl17_zpp', 'merged2_compressed', 'jpg2pdf', 'ilovepdf',
                      'declaracao de amesterdao 1208b']
    chunks = []
    for meta_file in sorted(CACHE_DIR.glob("*_meta.json")):
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        doc_name = meta.get("document", meta_file.stem.replace("_meta", "").replace("_", " "))
        doc_url = meta.get("url", "")

        # Skip admin/audit noise
        name_lower = doc_name.lower()
        if any(kw in name_lower for kw in admin_keywords):
            continue

        for page_data in meta.get("pages", []):
            text = page_data.get("text", "").strip()
            if not text or len(text) < 50:
                continue

            chunks.append({
                "text": text[:3000],
                "title": f"{doc_name} (S. {page_data['page']})",
                "url": f"{doc_url}#page={page_data['page']}" if doc_url else "",
                "date": "",
                "source": doc_name,
                "type": "policy",
                "page": page_data["page"],
            })
    return chunks


def load_html_chunks() -> list[dict]:
    """Load HTML policy text files (no _meta.json, just .txt from check_new_pdfs).
    Skips boilerplate pages with mostly navigation, menus, or less than ~200 chars of real content.
    """
    admin_keywords = ['chl17_zpp', 'merged2_compressed', 'jpg2pdf', 'ilovepdf',
                      'declaracao de amesterdao 1208b', 'data protection', 'anbi']
    boilerplate_patterns = [
        r'^(home|willkommen|welcome|news|presse|kontakt|impressum|login|register)',
        r'^navigation|menü|menu',
        r'cookies? akzeptieren|accept cookies',
    ]
    chunks = []
    seen_sources = set()
    for txt_file in sorted(CACHE_DIR.glob("*.txt")):
        # Skip news files and meta files
        if txt_file.name.startswith("news_") or txt_file.name.endswith("_meta.json"):
            continue
        meta_file = txt_file.with_name(txt_file.stem + "_meta.json")
        if meta_file.exists():
            continue  # Handled by load_pdf_chunks
        if txt_file.stat().st_size < 500:
            continue

        # Check if already in existing chunks (by full text equality)
        text = txt_file.read_text(encoding='utf-8', errors='replace').strip()
        if not text or len(text) < 500:
            continue

        source = txt_file.stem.replace("_", " ").replace("-", " ").strip()
        if source in seen_sources:
            continue
        # Skip admin/boilerplate sources
        src_lower = source.lower()
        if any(kw in src_lower for kw in admin_keywords):
            continue
        if re.match(r'^volt (dänemark|finnland|lettland|litauen)', src_lower):
            continue  # These only have nav, no real content
        
        # Check text quality: must have substantial content
        if sum(1 for line in text.split('\n') if len(line.strip()) > 50) < 3:
            continue  # Less than 3 lines with real content = boilerplate
        
        seen_sources.add(source)

        # Split into paragraphs for chunking
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 100]
        if not paragraphs:
            chunks.append({
                "text": text[:3000],
                "title": source,
                "url": "",
                "date": "",
                "source": source,
                "type": "policy",
            })
        else:
            for i, para in enumerate(paragraphs[:20]):
                chunks.append({
                    "text": para[:3000],
                    "title": f"{source} ({i+1})",
                    "url": "",
                    "date": "",
                    "source": source,
                    "type": "policy",
                })
    return chunks


def build_index():
    """Build or update FAISS index from all news + PDFs."""
    print("📦 Loading chunks...")

    # Load existing index + chunks if present
    existing_chunks = []
    if CHUNKS_PATH.exists():
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            existing_chunks = json.load(f)
        print(f"   Existing: {len(existing_chunks)} chunks")

    existing_texts = {c["text"][:200] for c in existing_chunks}

    # Gather new chunks
    news_chunks = load_news_chunks()
    pdf_chunks = load_pdf_chunks()
    html_chunks = load_html_chunks()
    all_chunks = news_chunks + pdf_chunks + html_chunks

    new_chunks = [c for c in all_chunks if c["text"][:200] not in existing_texts]

    if not new_chunks:
        print("   No new chunks to embed.")
        # Still rebuild FAISS from all existing chunks
        all_chunks = existing_chunks
    else:
        all_chunks = existing_chunks + new_chunks
        print(f"   New: {len(new_chunks)} chunks to embed")

    if not all_chunks:
        print("⚠️  No chunks found at all!")
        return

    print(f"\n📚 Total: {len(all_chunks)} chunks ({len(news_chunks)} news + {len(pdf_chunks)} pdf + {len(html_chunks)} html)")

    # Import sentence-transformers (first run downloads ~120MB model)
    print("\n🔄 Loading embedding model...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    print(f"   Model: {MODEL_NAME}")

    # Embed all chunks that don't have embeddings yet
    if new_chunks:
        texts = [c["text"][:2000] for c in new_chunks]
        print(f"   Embedding {len(texts)} new chunks...")
        new_embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
        print(f"   Done! Dimension: {new_embeddings.shape[1]}")
    else:
        new_embeddings = None

    # Build FAISS index
    import faiss
    import numpy as np

    dim = model.get_sentence_embedding_dimension()

    if INDEX_PATH.exists():
        # Load existing index and add new embeddings
        index = faiss.read_index(str(INDEX_PATH))
        if new_embeddings is not None:
            index.add(np.array(new_embeddings, dtype=np.float32))
        print(f"   Updated index: {index.ntotal} vectors")
    else:
        # Create new index
        index = faiss.IndexFlatIP(dim)  # Inner product = cosine similarity (normalized)
        if new_embeddings is not None:
            index.add(np.array(new_embeddings, dtype=np.float32))
        print(f"   Created new index: {index.ntotal} vectors")

        # Also embed existing chunks that were loaded from cache
        if existing_chunks and not new_chunks:
            texts = [c["text"][:2000] for c in existing_chunks]
            print(f"   Embedding {len(texts)} existing chunks...")
            existing_embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
            index.add(np.array(existing_embeddings, dtype=np.float32))
            print(f"   Index now: {index.ntotal} vectors")

    # Save
    print(f"\n💾 Saving...")
    faiss.write_index(index, str(INDEX_PATH))
    with open(CHUNKS_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    index_mb = INDEX_PATH.stat().st_size / 1024 / 1024
    print(f"   FAISS index: {INDEX_PATH} ({index_mb:.1f} MB)")
    print(f"   Chunks: {CHUNKS_PATH} ({len(all_chunks)} entries)")
    print(f"\n✅ Build complete! Index has {index.ntotal} vectors")


if __name__ == "__main__":
    build_index()
