#!/usr/bin/env python3
"""
Volt Policy MCP Server — für HuggingFace Spaces (SSE-Transport)
Startet am ersten Start eine Synchronisation des Cache-Repos,
danach wird der MCP-Server via SSE auf Port 7860 bereitgestellt.
"""
import os
import sys
import json
import subprocess
import shutil
from pathlib import Path

# --- Konfiguration ---
GIT_REPO = "https://github.com/harrytyp/voltpolicies.git"
CACHE_DIR = Path("/data/cache")  # HuggingFace Spaces persistenter Speicher
LOCAL_REPO = CACHE_DIR / "repo"
PORT = int(os.environ.get("PORT", 7860))  # HF Spaces Port

# --- Setup: Repo klonen / aktualisieren ---
def setup_cache():
    print("[SETUP] Initialisiere Cache...", flush=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    if LOCAL_REPO.exists():
        print("[SETUP] Bestehenden Cache aktualisieren...", flush=True)
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO), "pull", "--ff-only"],
            capture_output=True, timeout=60
        )
    else:
        print("[SETUP] Klone voltpolicies-Repo...", flush=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", GIT_REPO, str(LOCAL_REPO)],
            capture_output=True, timeout=120
        )
    
    # Prüfe ob Cache existiert
    cache_dir = LOCAL_REPO / "cache"
    if cache_dir.exists():
        print(f"[SETUP] Cache bereit: {len(list(cache_dir.glob('*')))} Dateien", flush=True)
        return str(LOCAL_REPO)
    else:
        print(f"[WARN] Kein Cache-Verzeichnis gefunden in {LOCAL_REPO}", flush=True)
        return str(LOCAL_REPO)

# --- MCP Server ---
repo_path = setup_cache()
sys.path.insert(0, str(Path(repo_path) / ".github" / "scripts"))
sys.path.insert(0, str(Path(repo_path)))

# Cache-Manager konfigurieren
os.environ["HERMES_SKILLS_CACHE_DIR"] = str(Path(repo_path) / "cache")

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
    try:
        from volt_policy_checker_enhanced import search_policies_enhanced
        results = search_policies_enhanced(query, max_results)
    except Exception as e:
        results = [{"error": str(e)}]
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
    try:
        from volt_policy_checker_enhanced import search_news_enhanced
        results = search_news_enhanced(query, max_results)
    except Exception as e:
        results = [{"error": str(e)}]
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
    try:
        from volt_policy_checker_enhanced import search_policies_enhanced, search_news_enhanced
        
        policy_results = search_policies_enhanced(statement)
        news_results = search_news_enhanced(statement)
        
        verdict = "NO_MATCH"
        confidence = "LOW"
        
        if policy_results and policy_results[0]["score"] >= 100:
            verdict = "MATCH"
            confidence = "HIGH"
        elif policy_results and policy_results[0]["score"] >= 30:
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
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def volt_verify_citation(citation: str) -> str:
    """Verify if a specific policy citation exists.
    
    Returns the matching document with URL and page number.
    
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
def volt_cache_status() -> str:
    """Show status of the local policy cache.
    
    Returns:
        JSON with cache info
    """
    try:
        from volt_policy_checker import get_cache_status
        status = get_cache_status()
    except Exception as e:
        status = {"error": str(e)}
    return json.dumps(status, indent=2, default=str)


@mcp.resource("volt://policies/list")
def list_policies() -> str:
    """List all available Volt policy documents with URLs."""
    try:
        cache_dir = Path(repo_path) / "cache"
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
        
        result = {"count": len(policies), "policies": policies}
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    print(f"[START] Volt Policy MCP Server auf Port {PORT} (SSE)", flush=True)
    mcp.run(transport="sse", host="0.0.0.0", port=PORT)
