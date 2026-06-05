#!/usr/bin/env python3
"""
Volt Policy MCP Server
Exposes Volt Europa/Germany policy search and checking as MCP tools.
Runs as a local stdio server — no hosting needed.
"""

import json
import sys
from pathlib import Path

# Add .github/scripts to path for imports
scripts_dir = Path(__file__).parent / ".github" / "scripts"
sys.path.insert(0, str(scripts_dir))

from cache_manager import get_cache_dir, load_config

# Create MCP server
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "volt-policies",
    instructions="Search and verify statements against Volt Europa and Volt Germany policy documents. Use volt_search for policy topics, volt_check to verify claims, volt_search_news for press mentions."
)


@mcp.tool()
def volt_search(query: str, max_results: int = 10) -> str:
    """Search Volt policy documents for a topic.
    
    Finds matching sections across all 32+ policy PDFs (MOPs, Grundsatzprogramm,
    Wahlprogramme, Positionspapiere, etc.).
    
    Args:
        query: Search term or phrase (e.g., "climate change", "nuclear energy")
        max_results: Maximum number of results to return (default 10)
    
    Returns:
        JSON with matching documents, relevance scores, and text excerpts
    """
    from volt_policy_checker import search_policies
    results = search_policies(query, max_results)
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_search_news(query: str, max_results: int = 10) -> str:
    """Search Volt news articles and press mentions.
    
    Searches cached RSS feeds from Volt Deutschland, Volt Europa,
    and "Volt in the Press" (Mastodon).
    
    Args:
        query: Search term (e.g., "defence", "ICC", "election")
        max_results: Maximum results (default 10)
    
    Returns:
        JSON with matching news articles, dates, and links
    """
    from volt_policy_checker import search_news
    results = search_news(query, max_results)
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_check(statement: str) -> str:
    """Check if a statement matches, contradicts, or relates to Volt policy.
    
    Cross-references the statement against all policy PDFs and news articles.
    Returns a verdict (MATCH, PARTIAL, CONTRADICTION, NEWS_REFERENCE, etc.)
    with confidence level and supporting evidence.
    
    Args:
        statement: The claim to verify (e.g., "Volt supports nuclear energy")
    
    Returns:
        JSON with verdict, confidence, matching policy sections, and news
    """
    from volt_policy_checker import check_consistency
    result = check_consistency(statement)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_verify_citation(citation: str) -> str:
    """Verify if a specific policy citation exists in the corpus.
    
    Checks if a section/chapter reference (like "MOP 9.0 Challenge 3, Section 2.1")
    actually exists in the policy documents.
    
    Args:
        citation: The citation to verify (e.g., "Challenge 5.1 - EU Reform")
    
    Returns:
        JSON with found/not found status and surrounding context
    """
    from volt_policy_checker import verify_citation
    result = verify_citation(citation)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def volt_fetch_news() -> str:
    """Fetch latest news from all RSS feeds.
    
    Pulls from Volt Deutschland, Volt Europa, and Mastodon "Volt in the Press".
    Updates the local cache.
    
    Returns:
        JSON with fetch summary (article counts per source)
    """
    from volt_policy_checker import fetch_all_news
    all_news = fetch_all_news()
    summary = {name: len(articles) for name, articles in all_news.items()}
    total = sum(summary.values())
    return json.dumps({"total": total, "by_source": summary}, indent=2)


@mcp.tool()
def volt_cache_status() -> str:
    """Show status of the local policy cache.
    
    Returns info about cached PDFs, text files, news feeds,
    and whether GitHub sync is configured.
    
    Returns:
        JSON with cache directory, counts, size, and sync status
    """
    from volt_policy_checker import get_cache_status
    status = get_cache_status()
    return json.dumps(status, indent=2, default=str)


@mcp.resource("volt://policies/list")
def list_policies() -> str:
    """List all available Volt policy documents in the corpus."""
    cache_dir = get_cache_dir()
    txts = sorted(cache_dir.glob("*.txt"))
    
    policies = []
    for txt in txts:
        name = txt.stem.replace("_", " ")
        size_kb = txt.stat().st_size / 1024
        source = "Volt Europa" if any(k in txt.name for k in ["MOP", "amsterdam", "Amsterdam", "Campaign", "Economic_Vision", "Electoral", "Energy", "Space", "European_Constitution", "Live_Animal"]) else "Volt Deutschland"
        policies.append({"name": name, "source": source, "size_kb": round(size_kb)})
    
    return json.dumps({"count": len(policies), "policies": policies}, indent=2)


@mcp.resource("volt://news/latest")
def latest_news() -> str:
    """Get the latest news articles from all feeds."""
    from volt_policy_checker import load_cached_news
    articles = load_cached_news()
    
    # Sort by date (newest first) and limit
    articles.sort(key=lambda x: x.get('date', ''), reverse=True)
    return json.dumps({"count": len(articles), "articles": articles[:20]}, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Run the MCP server via stdio
    mcp.run(transport="stdio")
