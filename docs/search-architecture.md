# Search Architecture

How semantic search, embeddings, and vector search work in this project.

---

## Overview

```
Documents (PDFs + HTML + News)
        │
        ▼
Chunking ──► Embedding ──► FAISS Index ──► Query
                    │                           │
                    │                           ▼
             multilingual                Cosine Similarity
             E5-small                    + Chapter Filter
```

Every document gets split into chunks, each chunk is embedded into a 384-dimensional vector using a multilingual transformer model. The vectors are stored in a FAISS index. A query follows the same embedding process, and FAISS returns the closest matching chunks by cosine similarity.

No translation, no keywords, no dictionaries. Search in any language supported by the model (100+ languages).

---

## 1. Chunking

Different document types are chunked differently:

| Source | Chunking strategy |
|--------|------------------|
| **PDFs** (via _meta.json) | One chunk per page. Each chunk is up to 3,000 characters. |
| **HTML policy pages** | Split on double newlines into paragraphs (>100 chars). Up to 20 paragraphs per page. |
| **News articles** | Title + description combined. Max 2,000 characters per article. |

Each chunk is a dict with: `text`, `title`, `url`, `date`, `source`, `type` (news/policy), and optionally `page` number.

---

## 2. Embedding Model

**Model:** `intfloat/multilingual-e5-small` (HuggingFace)

**Why this model:**
- 384-dimensional embeddings (compact, fast)
- Supports 100+ languages natively
- Small enough to run on CPU (~120 MB download)
- Optimized for cosine similarity via `normalize_embeddings=True`

**Usage:**
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("intfloat/multilingual-e5-small", trust_remote_code=True)
embeddings = model.encode(texts, normalize_embeddings=True)
```

The `normalize_embeddings=True` flag L2-normalizes every vector, so inner product (IP) search equals cosine similarity.

---

## 3. FAISS Index

**Type:** `IndexFlatIP` (Inner Product)

**Why IndexFlatIP:**
- Exact search (no approximations, no accuracy loss)
- With L2-normalized vectors, inner product = cosine similarity (range 0-1)
- Simple and reliable for up to ~1M vectors

**Size:** ~11 MB for 7,700 vectors at 384 dimensions.

Index file: `cache/faiss.index`
Chunk metadata: `cache/chunks.json` (parallel array, same order)

```python
import faiss
import numpy as np

# Load
index = faiss.read_index("cache/faiss.index")
index.ntotal  # number of vectors

# Search (returns distances + indices)
distances, indices = index.search(query_vector[np.float32], k=10)
```

---

## 4. Query Flow

```
"AI safety in Europe"
        │
        ▼
E5-small encode (same model, same normalize_embeddings=True)
        │
        ▼
384-dim vector, L2-normalized
        │
        ▼
FAISS IndexFlatIP.search(k=20)
        │
        ▼
Cosine similarity scores (0-1)
        │
        ▼
Look up chunks.json[index] for each result
        │
        ▼
Apply chapter/country filter (if requested)
        │
        ▼
Return top-k results with: text, title, url, score
```

The `volt_search` tool runs:
1. Embed query → 384-dim vector
2. FAISS search → pick top 20 (raw)
3. Filter by `chapters` parameter if given (matches `source` field in chunk metadata)
4. Return best matches with similarity score

---

## 5. Multilingual Search Without Translation

The E5-small model was trained on paired sentences across 100+ languages. A German sentence and an English sentence with similar meaning end up close in the 384-dimensional embedding space.

This means:
- A German query finds relevant French, Dutch, Polish policy documents
- No translation layer needed
- No keyword matching
- No language detection

Example: searching `"Wohnungspolitik"` finds Dutch `"huisvestingsbeleid"` and French `"logement"` policy sections, all ranked by semantic similarity.

---

## 6. Incremental Index Updates

When new documents are added, the index is updated incrementally:

1. Load existing `chunks.json` → build set of `existing_texts` (first 200 chars as fingerprint)
2. Process all documents → filter out any text already in the set
3. If new chunks exist: embed only the new ones, add to existing FAISS index
4. If no new chunks: skip embedding, keep existing index as-is
5. Save both `faiss.index` and `chunks.json`

This avoids re-embedding the entire corpus on every update.

---

## 7. Running It

```bash
# Build/update the index from scratch
python scripts/build_index.py

# Search from Python
python scripts/search_semantic.py

# Search via MCP
volt_search("AI regulation", max_results=5, chapters="DE,FR,EU")
```
