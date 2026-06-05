#!/usr/bin/env python3
"""
Volt Policy MCP Server (Enhanced)
Exposes Volt policy search with URLs, page numbers, and news links.
"""

import json
import sys
from pathlib import Path

# Add scripts to path
scripts_dir = Path(__file__).parent / ".github" / "scripts"
sys.path.insert(0, str(scripts_dir))

from cache_manager import get_cache_dir, load_config
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "volt-policies",
    instructions="Search and verify statements against Volt Europa and Volt Germany policy documents. Returns PDF URLs, page numbers, and direct news article links."
)


@mcp.tool()
def volt_search(query: str, max_results: int = 10) -> str:
    """Search Volt policy documents for a topic.
    
    Returns matching sections with PDF URLs, page numbers, and section headings.
    
    Args:
        query: Search term or phrase (e.g., "climate change", "UN Security Council")
        max_results: Maximum number of results to return (default 10)
    
    Returns:
        JSON with document name, PDF URL, page number, section heading, and text excerpt
    """
    from volt_policy_checker_enhanced import search_policies_enhanced
    results = search_policies_enhanced(query, max_results)
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_search_news(query: str, max_results: int = 10) -> str:
    """Search Volt news articles with direct article URLs.
    
    Args:
        query: Search term (e.g., "defence", "ICC", "election")
        max_results: Maximum results (default 10)
    
    Returns:
        JSON with title, direct URL, date, source, and description
    """
    from volt_policy_checker_enhanced import search_news_enhanced
    results = search_news_enhanced(query, max_results)
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_check(statement: str) -> str:
    """Check if a statement matches, contradicts, or relates to Volt policy.
    
    Returns verdict with PDF URLs, page numbers, and news article links.
    
    Args:
        statement: The claim to verify (e.g., "Volt supports nuclear energy")
    
    Returns:
        JSON with verdict, confidence, sources with URLs and pages
    """
    from volt_policy_checker import check_consistency, search_policies, search_news
    from volt_policy_checker_enhanced import search_policies_enhanced, search_news_enhanced
    
    # Get enhanced results
    policy_results = search_policies_enhanced(statement)
    news_results = search_news_enhanced(statement)
    
    # Determine verdict
    verdict = "NO_MATCH"
    confidence = "LOW"
    
    contradiction_keywords = ["not", "no", "against", "oppose", "reject", "deny"]
    support_keywords = ["support", "advocate", "promote", "favor", "propose"]
    has_contradiction = any(kw in statement.lower() for kw in contradiction_keywords)
    has_support = any(kw in statement.lower() for kw in support_keywords)
    
    if policy_results and policy_results[0]["score"] >= 100:
        verdict = "MATCH"
        confidence = "HIGH"
    elif policy_results and policy_results[0]["score"] >= 30:
        if has_contradiction:
            verdict = "POSSIBLE_CONTRADICTION"
        elif has_support:
            verdict = "PARTIAL_MATCH"
        else:
            verdict = "PARTIAL_MATCH"
        confidence = "MEDIUM"
    elif news_results and news_results[0]["score"] >= 50:
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
    """Verify if a specific policy citation exists.
    
    Returns the matching document with URL and page number.
    
    Args:
        citation: The citation to verify (e.g., "Challenge 5.1 - EU Reform")
    
    Returns:
        JSON with found/not found, URL, page, and context
    """
    from volt_policy_checker import verify_citation
    result = verify_citation(citation)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_fetch_news() -> str:
    """Fetch latest news from all RSS feeds.
    
    Returns:
        JSON with fetch summary
    """
    from volt_policy_checker import fetch_all_news
    all_news = fetch_all_news()
    summary = {name: len(articles) for name, articles in all_news.items()}
    total = sum(summary.values())
    return json.dumps({"total": total, "by_source": summary}, indent=2)


@mcp.tool()
def volt_cache_status() -> str:
    """Show status of the local policy cache.
    
    Returns:
        JSON with cache info
    """
    from volt_policy_checker import get_cache_status
    status = get_cache_status()
    return json.dumps(status, indent=2, default=str)


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
    from volt_policy_checker import load_cached_news
    articles = load_cached_news()
    articles.sort(key=lambda x: x.get('date', ''), reverse=True)
    return json.dumps({"count": len(articles), "articles": articles[:20]}, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
