# 🗺️ Volt Policies — Roadmap

> Conceptual improvements, architectural directions, and implementation paths.
> This document explores what the Volt Policies MCP tool *could* become.

---

## Table of Contents

1. [Why a Roadmap?](#why-a-roadmap)
2. [Hybrid Search (BM25 + Embeddings)](#1-hybrid-search-bm25--embeddings)
3. [Retriever-Augmented Generation (RAG)](#2-retriever-augmented-generation-rag)
4. [Cross-Chapter Comparison](#3-cross-chapter-comparison)
5. [Document Versioning & Change Detection](#4-document-versioning--change-detection)
6. [Policy Knowledge Graph](#5-policy-knowledge-graph)
7. [Automated Consistency Checks](#6-automated-consistency-checks)
8. [Real-Time Watchdog & Alerts](#7-real-time-watchdog--alerts)
9. [Evaluation & Quality Metrics](#8-evaluation--quality-metrics)
10. [Deployment Strategies](#9-deployment-strategies)

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

## 1. Hybrid Search (BM25 + Embeddings)

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

## 2. Retriever-Augmented Generation (RAG)

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

## 3. Cross-Chapter Comparison

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

## 4. Document Versioning & Change Detection

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

## 5. Policy Knowledge Graph

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

## 6. Automated Consistency Checks

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

## 7. Real-Time Watchdog & Alerts

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

## 8. Evaluation & Quality Metrics

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

## 9. Deployment Strategies

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
    │   🏛️ RAG Analysis        🔍 Hybrid Search
    │   ★★★★★                  ★★★★★
    │
    │   🕸️ Knowledge Graph     📊 Cross-Chapter
    │   ★★★★★                  ★★★★☆
    │
    │   ⚖️ Consistency          🕰️ Versioning
    │   ★★★★☆                  ★★★★☆
    │
    │   🔔 Watchdog            📏 Benchmark
    │   ★★★☆☆                  ★★★☆☆
    │
    └──────────────────────────────────→ Low Effort
         Low Effort                High Effort
```

**Low-hanging fruit:** Hybrid Search + Benchmark (~2 days)
**Transformative:** RAG Analysis + Cross-Chapter Comparison (~1 week)
**Visionary:** Knowledge Graph + Consistency Pipeline (~2–3 weeks)

---

*This roadmap is a living document. Contributions, corrections, and new ideas are welcome via Issues and Pull Requests.*
