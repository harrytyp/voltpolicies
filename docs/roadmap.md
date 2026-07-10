# 🗺️ Volt Policies — Roadmap

> Conceptual improvements, architectural directions, and implementation paths.
> This document explores what the Volt Policies MCP tool *could* become.

---

## Table of Contents

1. [Why a Roadmap?](#why-a-roadmap)
2. [Two-Axis Confidence Model (Grounding × Risk)](#1-two-axis-confidence-model-grounding--risk)
3. [Reranking (Cross-Encoder After FAISS)](#2-reranking-cross-encoder-after-faiss)
4. [Citation Gate / NLI Verification](#3-citation-gate--nli-verification)
5. [Hybrid Search (BM25 + Embeddings)](#4-hybrid-search-bm25--embeddings)
6. [Retriever-Augmented Generation (RAG)](#5-retriever-augmented-generation-rag)
7. [Cross-Chapter Comparison](#6-cross-chapter-comparison)
8. [Document Versioning & Change Detection](#7-document-versioning--change-detection)
9. [Policy Knowledge Graph](#8-policy-knowledge-graph)
10. [Automated Consistency Checks](#9-automated-consistency-checks)
11. [Real-Time Watchdog & Alerts](#10-real-time-watchdog--alerts)
12. [Evaluation & Quality Metrics](#11-evaluation--quality-metrics)
13. [Deployment Strategies](#12-deployment-strategies)

---

## Why a Roadmap?

The current tool is a **solid semantic search engine** over 7,300+ chunks from 33 Volt chapters. It answers "find me documents about X" very well. But there are several conceptual leaps between a search engine and a **policy intelligence system**:

| Gap | Current Behaviour | Desired Behaviour |
|-----|------------------|-------------------|
| **Synthesis** | Returns raw chunks, user must synthesize | Returns structured analysis with citations |
| **Time** | No versioning, latest document overwrites | Track positions across years |
| **Cross-reference** | Isolated per-query search | Compare chapters, find contradictions |
| **Structure** | Flat list of vectors | Hierarchical topic graph |
| **Verification** | Simple score threshold | Multi-step fact-checking pipeline |

The proposals below are ordered from **lowest effort / highest impact** to most ambitious.

---

## ⚡ Key Inspirations from Volt Relay

*The following three sections were inspired by [Volt Relay](https://volt-relay.vercel.app) — a sibling project building a comms-intelligence app for Volt chapters. Their design for confidence modelling, reranking, and citation verification is directly applicable to our research tool. See the full analysis below each feature.*

---

## 1. Two-Axis Confidence Model (Grounding × Risk)

### The Problem

Today `volt_check` returns a single verdict based on a cosine similarity threshold:

```python
if score >= 0.7 → MATCH (HIGH)
elif score >= 0.4 → PARTIAL_MATCH (MEDIUM)
else → NO_MATCH (LOW)
```

This is **one-dimensional**: it tells you how semantically close a chunk is, but not:
- **Where** the position comes from (EU-level policy? A local position paper? A blog post?)
- **How risky** it would be to cite publicly (is it on a sensitive topic? does it name an opponent?)
- **Whether a position actually exists** or the tool just found the closest noise

A user searching *"What does Volt say about nuclear energy?"* gets back a score of 0.53 with five chunks, but has no way to tell: *Is this an official adopted position or just one MEP's opinion?*

### What Volt Relay Does Differently

Volt Relay models confidence on **two independent axes**:

**Axis 1 — Grounding (where the line comes from)**

| Level | Meaning | Source |
|-------|---------|--------|
| europe | an adopted Europe-wide Volt position | the shared EU policy corpus |
| national | an adopted national-chapter position | the chapter's policy corpus |
| adhoc | a chapter-adopted ad-hoc stance (unofficial) | adopted in-app (no-line flow) |
| principle | no specific line, but a Volt principle applies | inferred, flagged as such |
| none | no Volt line on this topic yet | — |

**Axis 2 — Risk (how dangerous it is to cite)**

A result can be perfectly grounded and still risky. Risk is raised by: naming an opponent, a sensitive topic (migration, religion, defence), potential factual or legal exposure, off-brand tone, or internal inconsistency with a prior stance.

**Combined confidence (derived from both axes):**

```
🟢 Green  = grounded (europe/national/adhoc) AND low risk
           → publishable, quick read enough

🟠 Orange = principle-only OR medium risk
           → own the stance before citing

🔴 Red    = grounding none OR high risk
           → research before using
```

A grounded post can still be **red purely on risk** — e.g. a contrast post that names an opponent on a sensitive topic.

### Why This Matters for Volt Policies

Our users (researchers, journalists, policy analysts) need to know **not just that a result exists, but how much weight to give it**. A document from the EU-level Moonshot programme should be weighted higher than a local news article, even if both have similar cosine scores.

The single-axis score conflates two very different questions:
1. *"Is there a relevant policy?"* → Grounding
2. *"Should I cite it publicly?"* → Risk

### How It Would Work

**Step 1: Classify document type on ingest** — each chunk already carries a `source` field. Extend `build_index.py` to tag each chunk with a `grounding_level`:

```python
GROUDING_RULES = [
    ("mop 9.0", "europe"),
    ("moonshot", "europe"),
    ("amsterdam declaration", "europe"),
    ("election programme", "national"),
    ("wahlprogramm", "national"),
    ("grundsatzprogramm", "national"),
    ("position paper", "national"),
    ("incompatibility resolution", "national"),
    ("news", "principle"),
    # fallback: principle
]

def classify_grounding(source: str, title: str) -> str:
    source_lower = f"{source} {title}".lower()
    for keyword, level in GROUDING_RULES:
        if keyword in source_lower:
            return level
    return "principle"
```

**Step 2: Risk classification** — lightweight keyword-based classifier:

```python
RISK_KEYWORDS = {
    "high": ["migration", "religion", "defence", "military",
             "gegen", "opponent", "nuclear", "spionage"],
    "medium": ["reform", "steuer", "regulation", "eu reform",
               "incompatibility"],
}

def classify_risk(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in RISK_KEYWORDS["high"]):
        return "high"
    if any(kw in text_lower for kw in RISK_KEYWORDS["medium"]):
        return "medium"
    return "low"
```

**Step 3: Compute confidence**:

```python
CONFIDENCE_MATRIX = {
    ("europe", "low"):    "green",
    ("national", "low"):  "green",
    ("adhoc", "low"):     "green",
    ("principle", "low"): "orange",
    ("europe", "medium"): "green",
    ("national", "medium"): "orange",
    ("principle", "medium"): "orange",
    ("none", "low"):      "red",
    (_, "high"):          "red",
}
```

**Step 4: Expose in `volt_check`** — the tool returns both axes plus the derived colour:

```python
@mcp.tool()
def volt_check(statement: str, chapters: str = None) -> str:
    # ... existing retrieval ...
    return {
        "statement": statement,
        "confidence": {
            "level": "green",      # green / orange / red
            "grounding": "national",  # from document type
            "grounding_source": "Volt Deutschland BTW 2025 Programme",
            "risk": "low",            # from content analysis
            "risk_reason": None,      # "Sensitive topic: defence"
        },
        "sources": [...]
    }
```

### GitHub Implementation

- **File changes**: `mcp_server.py` (update `volt_check`), `build_index.py` (tag grounding on ingest), new `scripts/confidence.py`
- **Dependencies**: None — keyword-based classification needs no model download
- **Effort**: ~1-2 days, mostly testing edge cases on the risk rubric

### HuggingFace Implementation

The same logic runs identically in a Space — the classifier is pure Python with no GPU requirement. A Gradio tab could show a "Confidence Explorer" where users tweak the risk rubric and see how verdicts change.

### What Problem This Solves

> Users currently get a meaningless float score. After: they get an **actionable verdict** — green = safe to cite, orange = needs review, red = avoid. This is the single highest-leverage improvement because it requires no new infrastructure, no new models, and fundamentally changes how useful each result is.

---

## 2. Reranking (Cross-Encoder After FAISS)

### The Problem

FAISS with `IndexFlatIP` does **bi-encoder search**: query and document are independently embedded, then compared via cosine similarity. This is fast (sub-millisecond for 7K vectors) but misses nuance because the query and document never "see" each other during ranking.

A bi-encoder might rank:

```
Query: "What is Volt's position on EU defence?"

1. "Volt supports a European defence union" (score 0.72) ✓
2. "Volt Deutschland supports the Bundeswehr" (score 0.68) ✗ (wrong scope)
3. "Volt opposes defence spending cuts" (score 0.65) ? (context unclear)
```

A cross-encoder would correctly downgrade #2 because it can jointly attend to "EU defence" in the query vs. "Bundeswehr" (national) in the document. The cross-encoder sees the **relationship** between them; the bi-encoder only sees independent semantic fields.

### What Volt Relay Does Differently

Volt Relay uses **Cohere embed-v4 for retrieval + Cohere rerank-v3.5 for reranking**:

```
Query ──► FAISS (bi-encoder) ──► Top 50 ──► Reranker (cross-encoder) ──► Top 10
```

The reranker is a **cross-encoder**: it takes the query and each candidate document as a pair and outputs a relevance score. This is slower (O(n) forward passes for n candidates) but significantly more accurate because both texts are processed jointly by a transformer.

### Why This Matters for Volt Policies

Our index is only 7,300 vectors — small enough that reranking Top 50–100 candidates is trivial even on CPU. The quality gain is substantial:

| Aspect | Bi-encoder (current) | Cross-encoder (proposed) |
|--------|---------------------|--------------------------|
| Speed | ~1ms for 7K vectors | ~100-500ms for 50 pairs (CPU) |
| Ranking quality | Good (semantic fields) | Excellent (joint attention) |
| Query specificity | Misses query intent nuance | Context-aware relevance |
| Cross-lingual | Embedding alignment only | Joint understanding |
| Implementation | Already done | Add one model call |

Cross-encoders are particularly good at **disambiguating scope**: "EU defence policy" vs. "German defence policy" — a bi-encoder sees both as "defence" + "policy" and gives similar scores. A cross-encoder sees the full query context and correctly prioritises EU-level documents.

### How It Would Work

**Step 1: Add a cross-encoder model.** Load alongside the bi-encoder in `search_semantic.py`:

```python
# In search_semantic.py
_cross_encoder = None

def _load_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder("BAAI/bge-reranker-v2-m3")
    return _cross_encoder
```

`BAAI/bge-reranker-v2-m3` is a good choice because:
- Multilingual (trained on 100+ languages, matching our E5-small)
- Small enough for CPU (~1 GB download)
- Outputs a relevance score (0-1) directly comparable to our current scores

**Step 2: Optional reranking in search:**

```python
def semantic_search(query, max_results=10, chapters=None, rerank=True):
    index, chunks = _load_index()
    # Same bi-encoder first pass as today
    scores, indices = index.search(query_vec, k=50)  # Get more candidates
    
    # Rerank top 50 with cross-encoder
    if rerank and len(candidates) > max_results:
        pairs = [(query, c["text"]) for c in candidates]
        reranker = _load_cross_encoder()
        rerank_scores = reranker.predict(pairs)
        
        # Re-sort by reranker score
        for i, c in enumerate(candidates):
            c["score"] = float(rerank_scores[i])
        candidates.sort(key=lambda x: x["score"], reverse=True)
    
    return candidates[:max_results]
```

**Step 3: Expose as a parameter** so users can choose speed vs. accuracy:

```python
@mcp.tool()
def volt_search(query, max_results=10, chapters=None, rerank=True):
    """... rerank: use cross-encoder for better accuracy (slower) ..."""
```

### GitHub Implementation

- **File changes**: `scripts/search_semantic.py` (add cross-encoder loading + reranking step), `mcp_server.py` (expose `rerank` parameter)
- **Dependencies**: `sentence-transformers` already installed; CrossEncoder comes from the same package
- **Model**: `BAAI/bge-reranker-v2-m3` (1.1 GB download on first run)
- **Effort**: ~1-2 days, mostly testing cross-lingual quality

### HuggingFace Implementation

The cross-encoder loads once at startup on a Space. A GPU Space makes it near-instant, but CPU is fine for 50 pairs (~300ms per rerank pass). The Gradio search interface can add a "rerank" toggle.

### What Problem This Solves

> The bi-encoder returns **semantically related** results — not necessarily **relevantly related** to the specific query. Reranking cuts noise by ~30–50% in practice: the top 3 results after reranking are consistently on-topic, where the bi-encoder often includes tangentially related documents. For a research tool where users scan top-5 results, this directly translates to trust and efficiency.

---

## 3. Citation Gate / NLI Verification

### The Problem

When `volt_check` says *"Volt supports X (source: MOP 9.0, p. 12)"*, there is no guarantee that the chunk actually says that. The cosine similarity score tells us the chunk is *about the same topic* — not that it *supports the same claim*.

A search for *"Volt supports nuclear energy"* might return a chunk that says *"Volt opposes nuclear energy"* simply because both are about nuclear energy. The tool does not distinguish between:

| Retrieved chunk | Score | Reality |
|-----------------|-------|---------|
| "Volt supports a European nuclear deterrent" | 0.71 | SUPPORT | ← Correct |
| "Volt opposes nuclear energy on safety grounds" | 0.68 | OPPOSE | ← Wrong direction |
| "Nuclear energy is a complex issue requiring..." | 0.65 | NEUTRAL | ← Not a position |

Currently the user must manually read each chunk to determine directionality. This is **verification labour** that the tool should automate.

### What Volt Relay Does Differently

Volt Relay's **citation gate** runs after generation:

```
Draft with citations
    │
    ▼
Parse into (claim, citation) pairs
    │
    ├──► NLI entailment check: does citation support claim?
    │       • entailed → green (keeps citation)
    │       • neutral → orange (strips citation)
    │       • contradict → red (blocked)
    │
    └──► LLM fact-check on ambiguous pairs
```

**Natural Language Inference (NLI)** models are trained to classify the relationship between two texts:

- **ENTAILMENT**: The citation supports the claim (green)
- **CONTRADICTION**: The citation contradicts the claim (red — blocked)
- **NEUTRAL**: The citation is unrelated to the claim (orange — citation removed)

### Why This Matters for Volt Policies

Our current `volt_check` cannot distinguish **support from opposition**. An NLI gate would upgrade every result with a **stance label**:

```python
{
    "text": "Volt opposes nuclear energy on safety grounds",
    "claim": "Volt supports nuclear energy",
    "nli_verdict": "CONTRADICTION",  # ← New!
    "usable": False,
    "reason": "The cited document contradicts the claimed position"
}
```

This is transformative for fact-checking workflows. A journalist checking *"Does Volt support nuclear energy?"* gets not just chunks but a clear **for/against/neutral** verdict per source, plus an automatic flag when the claim contradicts the document.

### How It Would Work

**Step 1: Add an NLI model.** Many options, ordered by size:

| Model | Size | Languages | Quality |
|-------|------|-----------|---------|
| `MoritzLaurer/DeBERTa-v3-base-mnli-fever-docnli-ling-2c` | ~500 MB | 100+ | Excellent |
| `cross-encoder/nli-deberta-v3-base` | ~500 MB | EN (transfer to multilingual) | Very good |
| `microsoft/deberta-large-mnli` | ~1.5 GB | EN | Best for EN |

**Step 2: Verify every (claim, chunk) pair:**

```python
_nli_model = None

def _load_nli():
    global _nli_model
    if _nli_model is None:
        from transformers import pipeline
        _nli_model = pipeline(
            "zero-shot-classification",
            model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-docnli-ling-2c",
        )
    return _nli_model

def verify_claim(claim: str, chunk_text: str) -> dict:
    """Check whether chunk_text supports, contradicts, or is neutral to claim."""
    nli = _load_nli()
    result = nli(claim, [chunk_text], hypothesis_template="This text is about {}.")
    # Map to our categories
    label = result["labels"][0]  # highest score
    score = result["scores"][0]
    
    if label == "ENTAILMENT" and score > 0.6:
        return {"verdict": "SUPPORT", "score": score, "usable": True}
    elif label == "CONTRADICTION" and score > 0.6:
        return {"verdict": "CONTRADICT", "score": score, "usable": False}
    else:
        return {"verdict": "NEUTRAL", "score": score, "usable": False,
                "note": "Document is topically related but does not clearly support or oppose"}
```

**Step 3: Integrate into `volt_check`:**

```python
@mcp.tool()
def volt_check(statement: str, chapters: str = None, verify: bool = True) -> str:
    results = semantic_search(statement, max_results=5, chapters=ch)
    
    enhanced = []
    for r in results:
        entry = {**r}
        if verify:
            entry["verification"] = verify_claim(statement, r["text_preview"])
            if not entry["verification"]["usable"]:
                entry["confidence"]["level"] = "red"  # Downgrade
        enhanced.append(entry)
    
    return {"statement": statement, "results": enhanced, ...}
```

### Performance Considerations

NLI inference takes ~100-300ms per pair on CPU. For 5 results per query, that's ~0.5-1.5 seconds added — acceptable for an MCP tool. To keep latency low:
- Only run NLI when the `verify=True` flag is set
- Cache NLI results by (claim_hash, chunk_hash) — identical queries from different users reuse cached verdicts
- Limit to top 3-5 results (the ones users actually act on)

### GitHub Implementation

- **File changes**: `scripts/search_semantic.py` (add NLI verification), `mcp_server.py` (expose `verify` parameter)
- **Dependencies**: `transformers` + `torch` (already in the ecosystem; may need to add `torch`)
- **Model**: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-docnli-ling-2c` (~500 MB)
- **Effort**: ~3-4 days (model loading, edge cases, cross-lingual testing)

### HuggingFace Implementation

NLI models run on CPU (slow but functional) or GPU (near-instant). On HF Spaces:
- CPU: ~300ms per pair → adds ~1.5s per query — acceptable for a "verify" toggle
- T4 GPU: ~30ms per pair → almost free
- Cache with `datasets` or `joblib` on the persistent volume

### What Problem This Solves

> The tool's single biggest blind spot: it retrieves topically related documents but **cannot tell support from opposition**. A user checking "Does Volt support nuclear energy?" gets results about nuclear energy — period. NLI verification transforms this into an **actual answer**: "These 2 documents support, this 1 contradicts, and 2 are neutral." For a fact-checking/research tool this is the difference between useful and misleading.

---

## 4. Hybrid Search (BM25 + Embeddings)

### Problem

Pure embedding search (cosine similarity) is excellent for semantic paraphrasing but misses **exact keyword matches**. If a user searches for:

> *"Unvereinbarkeitsbeschluss Antisemitismus"*

…the embedding model may return pages about "incompatibility" and "anti-semitism" conceptually, but a BM25 keyword search would find the exact document title immediately. Similarly, specific citations like *"Challenge 5.1 – EU Reform"* benefit from lexical matching.

### How It Works

```
Query ──► BM25 (sparse) ──► RRF Fusion ──► Final results
       └─► Embeddings (dense) ──►
```

**Reciprocal Rank Fusion (RRF)** merges both result sets:

```python
score = 1 / (k + rank_bm25(result)) + 1 / (k + rank_dense(result))
```

### GitHub Implementation

Add a **hybrid search mode** to `scripts/search_semantic.py`:

```python
def hybrid_search(query, max_results=10, chapters=None):
    dense_results = semantic_search(query, max_results*2, chapters)
    sparse_results = bm25_search(query, max_results*2, chapters)
    return rrf_fuse(dense_results, sparse_results, k=60)
```

`bm25_search` needs a pre-built BM25 index (inverted term frequency). Build it alongside the FAISS index in `build_index.py` — store the BM25 term-document matrix as a pickle alongside `faiss.index`.

No additional dependencies beyond `scikit-learn` (which provides `TfidfVectorizer` + cosine similarity for a minimal BM25).

### HuggingFace Implementation

On HuggingFace Spaces, the BM25 index is built at startup (or pre-packaged). HuggingFace's `datasets` library can store the indexed corpus. The Space definition would:

1. Load FAISS index + BM25 matrix from the repo
2. Provide a Gradio interface with a slider for "hybrid vs. pure semantic" weight

---

## 5. Retriever-Augmented Generation (RAG)

### Problem

Today the MCP returns a list of chunks — the user (or calling LLM) must piece together a coherent answer. There's no structured synthesis. For a query like:

> *"Was ist Volts Position zur EU-Erweiterung?"*

The retriever returns 10 chunks from different documents. The user then has to manually identify: (a) which chunks support expansion, (b) which conditions Volt attaches, (c) whether there are chapter-specific differences. This is **synthesis work** that can be automated.

### How It Works

A new MCP tool `volt_analyze`:

```
Query ──► Retrieve top-k chunks ──► LLM prompt (structured) ──► JSON result
```

```python
@mcp.tool()
def volt_analyze(statement: str, chapters: str = None) -> str:
    """
    Analyze a statement against Volt policy.
    Returns a structured verdict with synthesis, supporting quotes,
    chapter-by-chapter breakdown, and direct source links.
    """
    chunks = retrieve(statement, chapters)
    prompt = build_analysis_prompt(statement, chunks)
    analysis = call_llm(prompt)  # local or API
    return json.dumps(analysis)
```

The prompt instructs the LLM to extract:

- **Consensus**: positions shared across chapters
- **Differences**: where chapters diverge
- **Evolution**: how positions change over time (if versioned)
- **Evidence**: verbatim quotes with URLs and page numbers
- **Confidence**: how strongly supported the conclusion is

The LLM call can use a small local model (Llama 3.2, Qwen 2.5) or an API (OpenRouter, together.ai) depending on the deployment.

### GitHub Implementation

The LLM call can be:
- **Lightweight**: use the Hermes MCP runtime's own LLM (if available) — zero extra infrastructure
- **Local**: bundle `llama-cpp-python` with a small 3B–8B model (~2–5 GB)
- **API**: configure an OpenRouter / Together AI endpoint in the environment

Add `scripts/analyze.py` with the prompt template. The MCP server calls it on demand.

### HuggingFace Implementation

HuggingFace Spaces with a **GPU upgrade** can run local inference:

- Space hardware: `T4 small` (1 GPU, 16 GB VRAM)
- Model: `Qwen/Qwen2.5-7B-Instruct-GGUF` via `llama-cpp-python`
- RAG pipeline: retrieve from FAISS → inject into prompt → stream response

For CPU-only Spaces, a smaller model like `microsoft/Phi-3-mini-4k-instruct` (3.8B) runs at ~30 tokens/sec on CPU via `llama.cpp`.

The Gradio interface adds a chat tab: "Ask a policy question" with real-time streaming.

---

## 6. Cross-Chapter Comparison

### Problem

Volt is a pan-European movement, but each national chapter adapts EU-level policy. Currently there's no way to ask:

> *"How do DE, FR, and IT differ on defence policy?"*

The user must run three separate `volt_search` calls and manually compare. This is tedious and error-prone.

### How It Works

A new tool `volt_compare`:

```python
@mcp.tool()
def volt_compare(topic: str, chapters: str) -> str:
    """
    Compare positions on a topic across multiple chapters.
    Returns a table with chapter → position summary.
    """
```

Internally it:
1. Runs `semantic_search(topic)` per chapter
2. Groups results by chapter
3. Identifies shared vs. unique statements
4. Computes **thematic overlap scores**: how aligned are two chapters on this topic?
5. Returns a structured comparison

### Data Representation

Each chunk already carries a `source` field (the chapter name). The comparison is a **group-by on source** with a **semantic clustering** step:

```python
# After retrieving per-chapter results:
for chapter in requested_chapters:
    chapter_chunks = filter_by_source(all_results, chapter)
    chapter_summary = summarize_position(chapter_chunks)
```

### HuggingFace Bonus

A **Dashboard Space** could visualize cross-chapter comparisons:

- Heatmap: "Chapter A vs. Chapter B alignment on topic X"
- Radar chart: each chapter's emphasis areas
- Timeline: how alignment changes over years (with versioning)

Built with Plotly or Observable Plot, updated on each index rebuild.

---

## 7. Document Versioning & Change Detection

### Problem

Today when Volt publishes a new election programme, the old one is replaced in the index. You cannot ask:

> *"How did Volt DE's position on housing change between 2021 and 2025?"*

Or:

> *"Did Volt EU drop its demand for a European army in the 2024 Moonshot update?"*

Without versioning, **temporal analysis is impossible**.

### How It Works

Instead of one `faiss.index`, maintain a **versioned index**:

```
cache/
├── v2021/
│   ├── faiss.index
│   └── chunks.json
├── v2025/
│   ├── faiss.index
│   └── chunks.json
└── latest -> v2025
```

Or simpler: store a `version` field per chunk in `chunks.json`. The index embeds all versions; queries filter by version.

```python
# Each chunk gets:
{
    "text": "...",
    "version": "2025-01-15",
    "document_version": "btw2025",
    # ...
}
```

When `build_index.py` finds a PDF URL it has already seen (via `known_pdfs.json`), it checks if the content changed. If so, it **appends** the new chunks with a new version tag rather than replacing.

### Change Detection

A dedicated tool:

```python
@mcp.tool()
def volt_diff(topic: str, chapter: str = None,
             from_version: str = None,
             to_version: str = None) -> str:
    """
    Show what changed in Volt's position on a topic between two versions.
    Returns added, removed, and modified statements.
    """
```

This uses **semantic diffing**: embed both versions' chunks, find chunks in `to_version` that have no close match in `from_version` (= added), and vice versa (= removed).

### GitHub Implementation

Extend `known_pdfs.json` to track checksums per URL. `scripts/check_new_pdfs.py` already checks for new PDFs; add a change-detection step that compares extracted text checksums. On change, the old text stays in the index with a `superseded_by` field.

### HuggingFace Implementation

Versioning is simpler on Spaces because the **persistent storage** (attached Volume) retains all historical index snapshots. A Space can offer a "Policy Timeline" tab that shows how any topic evolved.

---

## 8. Policy Knowledge Graph

### Problem

Policies are inherently hierarchical and interconnected. The current flat chunk representation loses:

- **Parent-child**: "MOP 9.0 Challenge 3 (Social Equality)" → "DE's housing policy" → "Position paper on rent control"
- **Cross-reference**: "Defence policy in DE" references "EU Moonshot 2029"
- **Theme clustering**: "AI", "digitalisation", "e-government" are all related but appear as independent chunks

Without structure, the system cannot answer:

> *"What EU-level policies has Volt DE implemented?"*

### How It Works

Build a **hierarchical topic taxonomy** from the document structure:

```
Smart State (MOP 9.0 C1)
  ├── E-Government
  │   ├── DE: Digitalverwaltungsgesetz
  │   ├── FR: État numérique 2030
  │   └── EU: Single Digital Gateway Regulation
  ├── AI Regulation
  │   ├── DE: Position paper on AI
  │   └── EU: AI Act support
  └── Data Sovereignty
```

Implementation:

1. **Document taxonomy extraction**: Parse Table of Contents from PDFs (many Volt documents have structured chapter/section headings)
2. **Hierarchical chunking**: Store parent/sibling/child references in chunk metadata
3. **Graph database** (optional): Use a lightweight graph (NetworkX or SQLite with recursive CTEs) to store relationships
4. **MCP tool**: `volt_graph(topic)` returns the subgraph as a JSON tree

```python
@mcp.tool()
def volt_graph(topic: str, depth: int = 2) -> str:
    """Show the policy tree around a topic.
    Returns parent policy → child implementations across chapters."""
```

### Implementation Without a Graph DB

The simplest approach: store a `path` field in each chunk:

```json
{
    "text": "...",
    "title": "Housing Policy (S. 12)",
    "path": "MOP9/C3/Social-Equality/Housing",
    "source": "Volt Deutschland",
    "parent_doc": "BTW 2025 Programme"
}
```

The path is extracted from the document's section hierarchy. Queries can then filter or group by path prefix — this is **prefix-tree search** and requires no graph infrastructure.

### HuggingFace Bonus

A **visual graph explorer** Space: an interactive D3.js/Force-Directed graph showing how policies connect. Clicking a node opens the relevant document chunk. Built with `networkx` + `pyvis` or a JavaScript frontend in a Gradio `HTML` component.

---

## 9. Automated Consistency Checks

### Problem

Volt claims to be "one movement with one programme" — but local chapters often adapt EU policy to national contexts. Sometimes these adaptations **contradict** the EU-level programme or other chapters' positions.

Currently **no tool checks for inconsistencies**. The Document Precedence rules (from README) are documentation only, not code:

> 1. Election programmes override basic programme
> 2. Position papers override basic programme
> 3. Basic programme overrides Moonshot 2029
> 4. Incompatibility resolutions are absolute
> 5. Amsterdam Declaration is foundational
> 6. News articles are supplementary

### How It Works

A new tool `volt_consistency`:

```python
@mcp.tool()
def volt_consistency(statement: str = None) -> str:
    """
    Check for contradictions across Volt policy documents.
    If statement is provided, check that specific claim.
    If omitted, scan for all known contradictions.
    """
```

**Implementation approach:**

1. Retrieve all chunks relevant to a topic across all chapters
2. **Clustering by stance**: use an LLM or a zero-shot classifier to group statements as:
   - SUPPORT: explicitly in favour
   - OPPOSE: explicitly against
   - CONDITIONAL: supports with conditions
   - NEUTRAL: factual/descriptive
3. If any chapter is in SUPPORT and another in OPPOSE on the same topic → **CONTRADICTION**
4. Apply Document Precedence rules to determine which document wins
5. Return a structured report with conflicting pairs

### Precedence-Aware Search

The search ranking itself should incorporate precedence:

```python
PRECEDENCE = {
    "election programme": 1.0,    # Highest
    "position paper": 0.9,
    "basic programme": 0.8,
    "moonshot": 0.7,
    "amsterdam declaration": 0.6,
    "incompatibility resolution": 1.0,  # Always absolute
    "news": 0.3,
}
```

Modify `semantic_search` to **boost scores** based on document type. This way, when contradictory evidence exists, the authoritative document appears first.

### GitHub Implementation

Add a `scripts/consistency.py` that runs as a scheduled CI job (e.g., weekly). It posts results as a GitHub Issue or check summary. The MCP tool makes it available on demand.

### HuggingFace Implementation

A dedicated "Consistency Dashboard" Space that visualises contradictions as a force-directed graph with red edges between contradictory positions. Updated after each index rebuild.

---

## 10. Real-Time Watchdog & Alerts

### Problem

Currently `volt_fetch_news()` runs once daily. If a Volt MEP posts something significant on Bluesky at 14:00, you won't see it until the next day's fetch. There's no way to **subscribe** to topics.

### How It Works

A lightweight watchdog that polls news sources more frequently (every 15–30 minutes) and checks new content against watched topics:

```python
@mcp.tool()
def volt_watch(topic: str, notify: bool = True) -> str:
    """Start watching a topic. New relevant content is flagged."""
```

Implementation:

1. Maintain a **watch list** (simple JSON file or in-memory)
2. On each news fetch, embed new articles and compare to watched topics
3. If cosine similarity > threshold → **generate alert**
4. Alert delivery: posted to a configured webhook, GitHub Discussion, or MCP resource

The `volt://news/latest` resource becomes `volt://news/alerts` — the latest alerts for watched topics.

### GitHub Implementation

Use **GitHub Actions scheduled at 15 min intervals** (up to 96 runs/day on the free tier) or a **cronjob** on the server. Alerts are posted as Issue comments or Discussion posts.

### HuggingFace Implementation

HuggingFace Spaces with **persistent storage** can run a background thread:

- A Gradio Space with a "Watch Topics" tab
- Background scheduler checks every 15 minutes
- New matches appear in a "Recent Alerts" panel
- Optional: email/webhook notification on match

---

## 11. Evaluation & Quality Metrics

### Problem

No one knows how good the search actually is. Is E5-small the best model for this domain? Does chunking at 2000 characters work? Are there blind spots in the index?

### How It Works

Create a **benchmark dataset** of 50–100 hand-curated query → expected document pairs:

```json
{
    "queries": [
        {
            "query": "What is Volt's position on nuclear energy?",
            "expected_docs": ["voltportugal_programa_politico_2022"],
            "expected_verdict": "SUPPORT",
            "language": "en"
        },
        ...
    ]
}
```

Then evaluate:

```python
@mcp.tool()
def volt_benchmark(model: str = "current") -> str:
    """
    Run the benchmark against the current or specified model.
    Returns NDCG@10, Recall@5, and per-query breakdown.
    """
```

Metrics:
- **NDCG@10**: Normalised Discounted Cumulative Gain (ranking quality)
- **Recall@5**: fraction of expected documents in top 5 results
- **Mean Reciprocal Rank (MRR)**: how early the first relevant result appears
- **Language Parity**: score stratified by query language — are small languages disadvantaged?

### A/B Testing

The benchmark enables **empirical model selection**:

```
Current: E5-small → NDCG@10 = 0.82
Test:    BGE-M3  → NDCG@10 = 0.89  ← Winner
Test:    E5-large-instruct → NDCG@10 = 0.91  ← Even better, but 4x slower
```

This data-driven approach justifies model upgrades and reveals coverage gaps.

### GitHub Implementation

Store the benchmark in `benchmarks/queries.json` and `benchmarks/relevance.json`. A CI workflow runs on push to `main` and on model changes. Results are committed to `benchmarks/results/latest.json` for tracking over time.

### HuggingFace Implementation

A "Quality Dashboard" Space with:
- Benchmark scores over time (line chart)
- Per-language breakdown (bar chart)
- Worst-performing queries list (actionable improvement targets)

---

## 12. Deployment Strategies

### GitHub (Current)

| Component | How | Schedule |
|-----------|-----|----------|
| CI Data Check | GitHub Actions (`update-news.yml`) | Daily @ 06:00 UTC |
| Index Rebuild | Server cron (`server_rebuild.sh`) | Daily @ 07:00 UTC |
| MCP Server | Standalone `mcp_server.py` (stdio) | On demand |
| Tools | Exposed via MCP to compatible clients | Real-time |

**Strengths:** Free CI/CD, git-based versioning, simple architecture.
**Limitations:** No synthesis (no LLM), batch-only news fetch, manual comparison.

### HuggingFace Spaces (Alternative)

| Component | How | Notes |
|-----------|-----|-------|
| **MCP Server** | Space with `mcp_server.py` via Gradio's API or FastAPI wrapper | Requires persistent hosting |
| **RAG Chat** | Gradio ChatInterface with retrieval + local LLM | GPU Space recommended |
| **Dashboard** | Gradio tabs: Search, Compare, Timeline, Consistency | CPU Space sufficient |
| **Index Build** | HF `Dataset` with FAISS integration | Leverages HF ecosystem |
| **Persistent Storage** | HF Space Persistent Storage (50 GB) | Retains index across restarts |
| **Scheduled Updates** | HF Space `sleep` timer or GitHub Actions → HF API | Keeps data fresh |

#### HuggingFace Architecture

```
┌─────────────────────┐
│   GitHub Repo       │  Raw data (PDFs, news, configs)
│   (data source)     │  Pushed from CI at 06:00 UTC
└────────┬────────────┘
         │ pull on startup + daily
         ▼
┌─────────────────────┐
│   HF Space: Index   │  Builds FAISS index from GitHub data
│   (CPU, 2 vCPU)     │  Stores on persistent volume
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   HF Space: Server  │  Runs MCP over Gradio API
│   (CPU or T4 GPU)   │  OR exposes FastMCP via SSE
└────────┬────────────┘
         │
         ┌───────────────┬────────────────┐
         ▼               ▼                ▼
    ┌─────────┐   ┌──────────┐   ┌──────────────┐
    │ MCP     │   │ RAG Chat │   │ Dashboard    │
    │ Clients │   │ (Gradio) │   │ (Gradio Tab) │
    └─────────┘   └──────────┘   └──────────────┘
```

#### HF Space Config (Minimal, MCP-only)

```yaml
# .space/Dockerfile or README.md metadata
---
sdk: gradio
sdk_version: 5.0
app_file: app.py
models:
  - intfloat/multilingual-e5-small
  - Qwen/Qwen2.5-7B-Instruct-GGUF  # optional for RAG
persistent_storage:
  size: 50Gi
```

```python
# app.py — wraps MCP in a Gradio frontend
import gradio as gr
import subprocess, json

def search(query, max_results=10, chapters=""):
    # Forward to MCP via subprocess
    proc = subprocess.run(
        ["python3", "mcp_server.py", "--tool", "volt_search",
         "--args", json.dumps({"query": query, "max_results": max_results})],
        capture_output=True, text=True, timeout=30
    )
    return proc.stdout

gr.Interface(search, ...).launch()
```

### Hybrid Approach (Recommended)

Keep the **GitHub repo as the data layer** (CI checks for new content, commits raw data). Use **HuggingFace Spaces as the serving layer** (MCP server, optional RAG chat, dashboards). The Spaces pull from GitHub on startup and daily via cron.

| Layer | Platform | Cost |
|-------|----------|------|
| Data collection & storage | GitHub Actions + Repo | Free |
| Index building & serving | HuggingFace Spaces (CPU) | Free (up to 2 vCPU) |
| Optional RAG (LLM inference) | HuggingFace Spaces (T4 GPU) | ~$0.60/hr |
| Consistency checks | GitHub Actions (weekly) | Free |
| Monitoring & alerts | GitHub Discussions + webhook | Free |

---

## 📈 Summary: Impact vs. Effort

```
High Impact
    │
    │   🟢 Confidence Model      🔍 Hybrid Search
    │   ★★★★★ (no deps!)         ★★★★★
    │
    │   📐 Reranking             🏛️ RAG Analysis
    │   ★★★★★                   ★★★★★
    │
    │   🛡️ Citation Gate         📊 Cross-Chapter
    │   ★★★★☆                   ★★★★☆
    │
    │   🕸️ Knowledge Graph       ⚖️ Consistency
    │   ★★★★★                   ★★★★☆
    │
    │   🕰️ Versioning            📏 Benchmark
    │   ★★★★☆                   ★★★☆☆
    │
    │   🔔 Watchdog
    │   ★★★☆☆
    │
    └──────────────────────────────────→ Low Effort
         Low Effort                High Effort
```

**Key insight from Volt Relay:** the three highest-leverage additions *(Confidence Model, Reranking, Citation Gate)* all follow the same pattern — they **upgrade existing retrieval with intelligence** rather than building new retrieval. Together they transform our search from *"here are some related documents"* to *"here is what Volt believes, how sure we are, and why we can prove it."*

**Low-hanging fruit:** Confidence Model + Benchmark (~1-2 days)
**Transformative:** Reranking + Citation Gate + RAG Analysis (~1 week)
**Visionary:** Knowledge Graph + Consistency Pipeline (~2-3 weeks)

---

*This roadmap is a living document. Contributions, corrections, and new ideas are welcome via Issues and Pull Requests. The first three sections were inspired by [Volt Relay](https://volt-relay.vercel.app) — a communications-intelligence sibling project for Volt chapters.*
