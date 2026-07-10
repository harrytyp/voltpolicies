# Volt Policies

Search Volt Europa and its **33 national chapters** for policies and news. Ask in any language. The search understands German, French, Dutch, Polish, Czech, and 100+ others natively.

Updated daily.

---

## 📊 Live Status

| | |
|---|---|
|| [→ STATUS.md](STATUS.md) | Corpus counts, CI status, last update |
|| [→ SOURCES.md](SOURCES.md) | Full list of documents & news sources with links |
|| [→ docs/roadmap.md](docs/roadmap.md) | Conceptual improvements & implementation plans |

*STATUS.md and SOURCES.md are auto-generated. Roadmap is a living document — contributions welcome.*

### 🗺️ Policy Coverage (28 of 33 countries)

| Status | Countries |
|--------|-----------|
| ✅ **PDF policies** | EU, DE, AT, BE, IT, NL, PT, RO, SK |
| ✅ **HTML policies** | AT, BE, CH, FR, NL, SE, IE, GB, HU, SI, EE, NO, ES, DK, PL, CZ, LU, MT, BG, HR, CY, AL, XK, GR, UA |
| ❌ **Missing** | FI, LV, LT (no public policy pages found) |

---

## 🚀 Quick Start

```bash
git clone https://github.com/harrytyp/voltpolicies.git
cd voltpolicies
pip install mcp pymupdf beautifulsoup4 sentence-transformers faiss-cpu

python scripts/build_index.py
python mcp_server.py
```

The cache directory is auto-detected from the project path. No configuration needed.

---

## 🔧 MCP Server Setup

```json
{
  "mcpServers": {
    "volt-policies": {
      "command": "python3",
      "args": ["/path/to/voltpolicies/mcp_server.py"]
    }
  }
}
```

### Tools

| Tool | What it does | Returns |
|------|-------------|---------|
| `volt_search(query, max_results, chapters)` | Search policies across 33 chapters in any language | Document, URL#page, excerpt, score |
| `volt_search_news(query, max_results, chapters)` | Search news from RSS, Bluesky, Mastodon | Title, URL, date, description, score |
| `volt_check(statement)` | Check a claim against Volt policy | Verdict, sources, URLs |
| `volt_verify_citation(citation)` | Verify if a citation exists in the index | Found/not found, URL, page |
| `volt_fetch_news()` | Refresh all news feeds | Article counts |
| `volt_cache_status()` | Show cache info | Directory, counts, size |
| `volt_list_chapters()` | List all 33 Volt national chapters | Chapter names, country codes |

Filter by country code with the `chapters` parameter:
```
volt_search("climate change", chapters="DE,FR,IT")
volt_search_news("Wohnungspolitik", chapters="AT")
```

### Resources
| `volt://policies/list` | List all policy documents with URLs |
| `volt://news/latest` | Get the 20 most recent news articles with direct links |

---

## 🌍 How Search Works

Every document and news article is embedded into a 384-dimensional vector using **E5-small** (multilingual). Your query is embedded the same way, and FAISS finds the closest matches by cosine similarity.

The result: search works in any language without translation or keyword matching. A German query finds relevant French policies, and vice versa.

```
Query → E5-small embed → FAISS IndexFlatIP → Top-k results → Chapter filter → Results
```

---

## 📱 Data Sources

**33 national chapters.** RSS feeds plus paginated website scraping for all Volt chapters. The scraper stops automatically when no more articles are found.

**Bluesky.** 5 accounts via the public AT Protocol (no login required):
- `voltdeutschland.org` Volt Deutschland
- `volteuropa.org` Volt Europa
- `annastrolenberg.volteuropa.org` Anna Strolenberg (MEP)
- `reiniervanlanschot.volteuropa.org` Reinier van Lanschot (MEP)
- `sophieintveld.bsky.social` Sophie in 't Veld (MEP)

**Mastodon.** `@voltinthepress` via the public Mastodon API.

---

## 🔄 Daily Updates

**CI (GitHub Actions)** runs every day at **06:00 UTC**:
1. Checks Volt websites for new PDFs and HTML policy pages
2. Fetches news from RSS, website scraping, Bluesky, and Mastodon
3. Commits any new raw data to the repository

**Server cronjob** runs every day at **07:00 UTC**:
1. Pulls the latest data from GitHub
2. Rebuilds the FAISS semantic index
3. Generates STATUS.md and SOURCES.md
4. Pushes the updated index back

Manual trigger:
```bash
gh workflow run update-news.yml      # CI check
bash scripts/server_rebuild.sh        # Server index rebuild
```

---

## 📁 Repository Layout

```
voltpolicies/
├── .github/
│   ├── workflows/
│   │   └── update-news.yml        ← CI: daily at 06:00 UTC
│   └── scripts/
│       ├── cache_manager.py       ← Cache path resolution
│       ├── fetch_news.py          ← Multi-source news fetcher
│       ├── check_new_pdfs.py      ← Checks for new PDFs/HTML
│       ├── generate_status.py     ← Generates STATUS.md
│       └── generate_sources.py    ← Generates SOURCES.md
├── scripts/
│   ├── build_index.py             ← FAISS index builder
│   ├── search_semantic.py         ← FAISS search logic
│   ├── server_rebuild.sh          ← Server-side index rebuild
│   ├── chapters.json              ← 33 chapter configs
│   ├── fetch_bluesky.py           ← Bluesky post crawler
│   └── fetch_instagram.py         ← Instagram fetcher (login required)
├── cache/
│   ├── faiss.index                ← FAISS index (~11 MB, 7,500+ vectors)
│   ├── chunks.json                ← Metadata per indexed chunk
│   ├── *.txt / *_meta.json        ← Extracted policy text (400+ docs)
│   └── news_*.json                ← News articles per chapter
├── mcp_server.py                  ← MCP server (stdio)
├── known_pdfs.json                ← PDF URL registry
├── STATUS.md                      ← Auto-generated: live counts
├── SOURCES.md                     ← Auto-generated: full source list
├── .gitignore
└── README.md
```

---

## Document Precedence

When the tools find conflicting policy statements, this is the priority order:
1. Election programmes override the basic programme on campaign topics
2. Position papers override the basic programme on specific topics
3. Basic programme overrides the Moonshot 2029 programme (MOP 9.0)
4. Incompatibility resolutions are absolute
5. Amsterdam Declaration is foundational
6. News articles are supplementary

|---

## 🔮 Future Directions

This project has grown from a simple search tool into a **policy intelligence system**. The [roadmap](docs/roadmap.md) explores where it could go next:

| Direction | What it solves | Effort |
|-----------|---------------|--------|
| **Hybrid Search** (BM25 + embeddings) | Keyword misses in pure semantic search | Low |
| **RAG Analysis** | Raw chunks → structured answers with citations | Medium |
| **Cross-Chapter Comparison** | Manual multi-query comparison across countries | Medium |
| **Versioning & Change Detection** | Track policy evolution over time | Medium |
| **Knowledge Graph** | Flat chunks → hierarchical topic structure | High |
| **Consistency Checks** | Find contradictions across chapters | Medium |
| **Real-Time Watchdog** | Topic monitoring with push alerts | Medium |
| **Quality Benchmark** | Measure and improve retrieval accuracy | Low |
| **HuggingFace Spaces** | Dashboard, RAG chat, visualisation | Medium |

See [docs/roadmap.md](docs/roadmap.md) for full details and implementation strategies on GitHub and HuggingFace.

---

| Variable | Purpose |
|----------|---------|
| `VOLT_CACHE_DIR` | Override the cache directory if auto-detection doesn't suit you |
