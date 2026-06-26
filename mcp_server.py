#!/usr/bin/env python3
"""
Volt Policy MCP Server (Enhanced with FAISS Semantic Search + Chapter Filtering)
Exposes Volt policy search with multilingual embeddings, URLs, page numbers, and news links.
Supports selective search by country chapter (33 national chapters).
"""

import json
import sys
from pathlib import Path

# Add .github/scripts for existing tools
scripts_dir = Path(__file__).parent / ".github" / "scripts"
sys.path.insert(0, str(scripts_dir))

# Add our scripts for semantic search
semantic_dir = Path(__file__).parent / "scripts"
sys.path.insert(0, str(semantic_dir))

from cache_manager import get_cache_dir, load_config
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "volt-policies",
    instructions="Search and verify statements against Volt Europa and all 33 national chapter policy documents and news. "
                 "Supports filtering by country/chapter. Returns PDF URLs, page numbers, and direct news article links. "
                 "Uses semantic search (multilingual FAISS embeddings) — queries work in any language across all chapter languages."
)

# Load chapters config for listing
CHAPTERS_PATH = Path(__file__).parent / "scripts" / "chapters.json"
CHAPTERS = {}
if CHAPTERS_PATH.exists():
    with open(CHAPTERS_PATH, 'r', encoding='utf-8') as f:
        raw = json.load(f)
        CHAPTERS = raw.get("chapters", {})


def _parse_chapters(chapters: str | list[str] | None) -> list[str] | None:
    """Convert various chapter input formats to a list, or None for no filter."""
    if chapters is None:
        return None
    if isinstance(chapters, str):
        chapters = [c.strip() for c in chapters.split(",") if c.strip()]
    if isinstance(chapters, list):
        chapters = [c.strip() for c in chapters if c and c.strip()]
    return chapters if chapters else None


@mcp.tool()
def volt_search(query: str, max_results: int = 10, chapters: str = None) -> str:
    """Search Volt policy documents for a topic.

    Uses semantic search (multilingual FAISS embeddings) — queries work in any language
    across all 33 national chapters. English is universal fallback.

    Args:
        query: Search term or phrase (e.g., "climate change", "UN Security Council")
        max_results: Maximum number of results to return (default 10)
        chapters: Optional filter — comma-separated country codes or chapter names.
                 Examples: "DE" (Germany only), "EU,DE,FR" (EU + Germany + France),
                 "Volt Österreich", "all" (all chapters, default).
                 Use volt_list_chapters() to see all available.

    Returns:
        JSON with document name, PDF URL, page number, section heading, and text excerpt
    """
    from search_semantic import semantic_search, index_available

    if not index_available():
        return json.dumps({"error": "No semantic index found. Run build_index.py first."}, indent=2)

    ch = _parse_chapters(chapters)
    results = semantic_search(query, max_results, chapters=ch)
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_search_news(query: str, max_results: int = 10, chapters: str = None) -> str:
    """Search Volt news articles with direct article URLs.

    Uses semantic search (multilingual FAISS embeddings) — queries work in any language
    across all 33 national chapters. English is universal fallback.

    Args:
        query: Search term (e.g., "defence", "ICC", "election")
        max_results: Maximum results (default 10)
        chapters: Optional filter — comma-separated country codes or chapter names.
                 Examples: "DE" (Germany only), "EU,DE,FR,IT,ES",
                 "Volt Österreich News", "all" (default).
                 Use volt_list_chapters() to see all available.

    Returns:
        JSON with title, direct URL, date, source, and description
    """
    from search_semantic import semantic_search, index_available

    if not index_available():
        return json.dumps({"error": "No semantic index found. Run build_index.py first."}, indent=2)

    ch = _parse_chapters(chapters)
    results = semantic_search(query, max_results, chapters=ch)
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_check(statement: str, chapters: str = None) -> str:
    """Check if a statement matches, contradicts, or relates to Volt policy.

    Returns verdict with PDF URLs, page numbers, and news article links.
    Uses semantic search (multilingual FAISS embeddings).

    Args:
        statement: The claim to verify (e.g., "Volt supports nuclear energy")
        chapters: Optional filter — comma-separated country codes or chapter names.
                 Narrow to specific countries for more targeted results.
                 Use volt_list_chapters() to see all available.

    Returns:
        JSON with verdict, confidence, sources with URLs and pages
    """
    from search_semantic import semantic_search, index_available

    if not index_available():
        return json.dumps({"error": "No semantic index found. Run build_index.py first."}, indent=2)

    ch = _parse_chapters(chapters)

    policy_results = semantic_search(statement, max_results=5, chapters=ch)
    news_results = semantic_search(statement, max_results=5, chapters=ch)

    # Determine verdict based on top scores
    verdict = "NO_MATCH"
    confidence = "LOW"

    if policy_results and policy_results[0]["score"] >= 0.7:
        verdict = "MATCH"
        confidence = "HIGH"
    elif policy_results and policy_results[0]["score"] >= 0.4:
        verdict = "PARTIAL_MATCH"
        confidence = "MEDIUM"
    elif news_results and news_results[0]["score"] >= 0.5:
        verdict = "NEWS_REFERENCE"
        confidence = "MEDIUM"

    analysis = {
        "statement": statement,
        "verdict": verdict,
        "confidence": confidence,
        "sources": policy_results[:3],
        "news": news_results[:3]
    }

    return json.dumps(analysis, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_verify_citation(citation: str) -> str:
    """Verify if a specific policy citation exists in the documents.

    Falls back to keyword search for exact citation matching.

    Args:
        citation: The citation to verify (e.g., "Challenge 5.1 - EU Reform")

    Returns:
        JSON with found/not found, URL, page, and context
    """
    try:
        from volt_policy_checker import verify_citation
        result = verify_citation(citation)
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_fetch_news() -> str:
    """Fetch latest news from all RSS feeds.

    Returns:
        JSON with fetch summary
    """
    try:
        from volt_policy_checker import fetch_all_news
        all_news = fetch_all_news()
        summary = {name: len(articles) for name, articles in all_news.items()}
        total = sum(summary.values())
        return json.dumps({"total": total, "by_source": summary}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def volt_cache_status() -> str:
    """Show status of the local policy cache and FAISS index.

    Returns:
        JSON with cache info, index status, vector count
    """
    import search_semantic
    index_ok = search_semantic.index_available()

    cache_dir = get_cache_dir()
    news_files = list(cache_dir.glob("news_*.json"))
    meta_files = list(cache_dir.glob("*_meta.json"))

    # Count news articles
    total_news = 0
    for nf in news_files:
        try:
            with open(nf, 'r', encoding='utf-8') as f:
                total_news += len(json.load(f))
        except:
            pass

    vector_count = 0
    if index_ok:
        try:
            idx, _ = search_semantic._load_index()
            if idx is not None:
                vector_count = idx.ntotal
        except:
            pass

    status = {
        "index": {
            "available": index_ok,
            "path": str(search_semantic.INDEX_PATH) if index_ok else None,
            "vector_count": vector_count,
            "model": "intfloat/multilingual-e5-small",
        } if index_ok else {"available": False},
        "pdf_count": len(meta_files),
        "news_files": len(news_files),
        "total_articles": total_news,
        "cache_dir": str(cache_dir),
    }
    return json.dumps(status, indent=2, default=str)


@mcp.tool()
def volt_list_chapters() -> str:
    """List all available Volt national chapters with country codes.

    Use this to see which chapters you can filter by in volt_search,
    volt_search_news, and volt_check. You can filter by country code
    (e.g. "DE", "FR", "IT") or by chapter name (e.g. "Volt Österreich").

    Returns:
        JSON with list of chapters, country codes, and websites
    """
    chapters_list = []
    # Add EU
    chapters_list.append({
        "code": "EU",
        "name": "Volt Europa",
        "website": "https://volteuropa.org",
        "type": "pan-european"
    })
    for name, info in sorted(CHAPTERS.items()):
        chapters_list.append({
            "code": info.get("country", "??"),
            "name": name,
            "website": info.get("website", ""),
            "type": "national"
        })
    return json.dumps({"count": len(chapters_list), "chapters": chapters_list}, indent=2, ensure_ascii=False)


@mcp.resource("volt://policies/list")
def list_policies() -> str:
    """List all available Volt policy documents with URLs."""
    cache_dir = get_cache_dir()
    meta_files = sorted(cache_dir.glob("*_meta.json"))

    policies = []
    for meta_file in meta_files:
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        policies.append({
            "name": meta.get("document", ""),
            "url": meta.get("url", ""),
            "pages": len(meta.get("pages", []))
        })

    return json.dumps({"count": len(policies), "policies": policies}, indent=2)


@mcp.resource("volt://news/latest")
def latest_news() -> str:
    """Get the latest news articles with direct URLs."""
    try:
        from volt_policy_checker import load_cached_news
        articles = load_cached_news()
        articles.sort(key=lambda x: x.get('date', ''), reverse=True)
        return json.dumps({"count": len(articles), "articles": articles[:20]}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
