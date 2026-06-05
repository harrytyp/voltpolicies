#!/usr/bin/env python3
"""
Volt Policy Reference Checker
Downloads Volt Europa and Volt Deutschland policy PDFs,
fetches news via RSS feeds, extracts text, and cross-references
against input statements.

Supports cross-device sync via GitHub repo (see cache_manager.py).
"""

import os
import sys
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# Import cache manager for configurable paths
sys.path.insert(0, str(Path(__file__).parent))
from cache_manager import get_cache_dir, load_config

# PDF URLs - Volt Europa
VOLT_EUROPA_PDFS = {
    "Amsterdam Declaration": "https://volteuropa.org/storage/pdf/policies/amsterdam_declaration.pdf",
    "Amsterdam Declaration (Supporting)": "https://volteuropa.org/storage/pdf/policies/supporting_document_amsterdam_declaration.pdf",
    "Campaign Narrative 2024": "https://volteuropa.org/storage/pdf/eu-elections-2024/campaign-narrative-2024-eu-elections.pdf",
    "MOP 9.0 - Smart State": "https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-1-smart-state.pdf",
    "MOP 9.0 - Economic Renaissance": "https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-2-economic-renaissance.pdf",
    "MOP 9.0 - Social Equality": "https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-3-social-equality.pdf",
    "MOP 9.0 - Global Balance": "https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-4-global-balance.pdf",
    "MOP 9.0 - Citizen Empowerment": "https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-5-citizen-empowerment.pdf",
    "MOP 9.0 - EU Reform": "https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-5-1-eu-reform.pdf",
    "Economic Vision": "https://volteuropa.org/storage/pdf/policies/the-economic-vision-of-volt-europa-final.pdf",
    "Electoral Reform": "https://volteuropa.org/storage/pdf/policies/electoral-reform-policy.pdf",
    "Energy Transition & Climate Change": "https://volteuropa.org/storage/pdf/policies/energy-transition-&-climate-change.pdf",
    "Space Policy": "https://volteuropa.org/storage/pdf/policies/volt-space-policy.pdf",
    "European Constitution": "https://volteuropa.org/storage/pdf/policies/provisions-for-a-european-constitution.pdf",
    "Live Animal Transportation": "https://volteuropa.org/storage/pdf/policies/regulation-of-live-animal-transportation.pdf",
}

# PDF URLs - Volt Deutschland
VOLT_DEUTSCHLAND_PDFS = {
    # Statuten
    "Satzung": "https://voltdeutschland.org/storage/assets-de/pdf/statuten_de/satzung-von-volt-deutschland.pdf",
    "Finanzordnung": "https://voltdeutschland.org/storage/assets-de/pdf/statuten_de/finanzordnung-von-volt-deutschland.pdf",
    "Schiedsgerichtsordnung": "https://voltdeutschland.org/storage/assets-de/pdf/statuten_de/schiedsgerichtsordnung-von-volt-deutschland.pdf",
    "Allgemeine Wahlordnung": "https://voltdeutschland.org/storage/assets-de/pdf/statuten_de/allgemeine-wahlordnung-von-volt-deutschland.pdf",
    "Geschäftsordnung Bundesparteitage": "https://voltdeutschland.org/storage/assets-de/pdf/statuten_de/geschaftsordnung-fur-ordentliche-und-ausserordentliche-bundesparteitage-von-volt-deutschland-1.pdf",
    "Geschäftsordnung Online-Bundesparteitage": "https://voltdeutschland.org/storage/assets-de/pdf/statuten_de/volt-deutschland-go-obpt-202602.pdf",
    # Programme
    "Grundsatzprogramm 2023": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/grundsatzprogramm_volt_deutschland_2023_01_28.pdf",
    # Wahlprogramme (no Kurzwahlprogram)
    "Bundestagswahl 2025": "https://voltdeutschland.org/storage/assets-btw25/volt-programm-bundestagswahl-2025.pdf",
    "Bundestagswahl 2025 (Leichte Sprache)": "https://voltdeutschland.org/storage/assets-de/pdf/btw-wahl-2025/gepruftes-wahl-programm-leichte-sprache-volt-bundestags-wahl-2025.pdf",
    "Europawahl 2024": "https://voltdeutschland.org/storage/assets-de/pdf/europawahl_2024/volt-wahlprogramm-europawahl-2024.pdf",
    # Positionspapiere
    "Position: Ehegattensplitting": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/ehegattensplitting-stufenweise-abschaffen-(1).pdf",
    "Position: Wehrfähige EU": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/positionspapier-wehrfahige-eu-2-ziel-als-mindestsatz-fur-eine-eu-kompatible-vollausstattung-der-bundeswehr.pdf",
    "Position: Nukleare Teilhabe": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/nukleare-teilhabe-in-europa-neu-denken-1.pdf",
    "Position: Magnetschwebebahn": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/positionspapier-_magnetschwebebahn-potenziale-fur-eine-zukunftsfeste-mobilitat-nutzen_-(veroffentlichte-version).pdf",
    # Unvereinbarkeitsbeschlüsse
    "Unvereinbarkeit: Antisemitismus": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/unvereinbarkeitsbeschluss-antisemitismus-und-zum-schutz-judischen-lebens.pdf",
    "Unvereinbarkeit: Rechtsextremismus": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/unvereinbarkeitsbeschluss-fur-jegliche-zusammenarbeit-mit-rassistischen,-rechtsextremen,-demokratie-und-verfassungsfeindlichen-gruppierungen-und-parteien,-insbesondere-der-afd-(1).pdf",
    "Unvereinbarkeit: Linksextremismus": "https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/unvereinbarkeitsbeschluss-linksextremismus-(1).pdf",
}

# RSS Feeds
RSS_FEEDS = {
    "Volt Deutschland News": "https://voltdeutschland.org/neuigkeiten/rss",
    "Volt Europa News": "https://volteuropa.org/news/rss",
    "Volt in the Press (Mastodon)": "https://mastodon.social/@voltinthepress.rss",
}


def ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def download_pdf(name: str, url: str) -> Path:
    """Download a PDF and cache it locally."""
    cache_dir = get_cache_dir()
    safe_name = re.sub(r'[^\w\-]', '_', name)
    pdf_path = cache_dir / f"{safe_name}.pdf"
    
    if pdf_path.exists():
        # Check if file is less than 7 days old
        age_days = (datetime.now().timestamp() - pdf_path.stat().st_mtime) / 86400
        if age_days < 7:
            return pdf_path
    
    print(f"Downloading: {name}...")
    
    # Try curl first (more reliable on Windows)
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", str(pdf_path), url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 1000:
            return pdf_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Fallback to requests
    try:
        import requests
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        pdf_path.write_bytes(response.content)
        return pdf_path
    except Exception as e:
        print(f"  Warning: Failed to download {name}: {e}")
        return None


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF using pymupdf (fitz)."""
    cache_dir = get_cache_dir()
    txt_path = cache_dir / f"{pdf_path.stem}.txt"
    
    if txt_path.exists():
        return txt_path.read_text(encoding='utf-8', errors='replace')
    
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text() + "\n\n"
        doc.close()
        
        txt_path.write_text(text, encoding='utf-8')
        return text
    except ImportError:
        print("  Warning: pymupdf not installed. Install with: pip install pymupdf")
        return ""
    except Exception as e:
        print(f"  Warning: Failed to extract text from {pdf_path.name}: {e}")
        return ""


def fetch_rss_feed(name: str, url: str) -> list:
    """Fetch and parse an RSS feed, returning list of articles."""
    import subprocess
    
    print(f"Fetching RSS: {name}...")
    
    # Fetch feed content
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  Warning: Failed to fetch {name}")
            return []
        feed_content = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback to requests
        try:
            import requests
            response = requests.get(url, timeout=30)
            feed_content = response.text
        except Exception as e:
            print(f"  Warning: Failed to fetch {name}: {e}")
            return []
    
    # Parse RSS/Atom feed
    articles = []
    try:
        root = ET.fromstring(feed_content)
        
        # Handle different feed formats
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        # Try RSS 2.0 format
        for item in root.findall('.//item'):
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            description = item.findtext('description', '')
            pub_date = item.findtext('pubDate', '')
            
            if title or link:
                articles.append({
                    'title': title.strip(),
                    'link': link.strip(),
                    'description': description.strip()[:500],
                    'date': pub_date.strip(),
                    'source': name
                })
        
        # Try Atom format if no RSS items found
        if not articles:
            for entry in root.findall('.//atom:entry', ns):
                title = entry.findtext('atom:title', '', ns)
                link_elem = entry.find('atom:link', ns)
                link = link_elem.get('href', '') if link_elem is not None else ''
                summary = entry.findtext('atom:summary', '', ns) or entry.findtext('atom:content', '', ns)
                updated = entry.findtext('atom:updated', '', ns)
                
                if title or link:
                    articles.append({
                        'title': title.strip(),
                        'link': link.strip(),
                        'description': (summary or '').strip()[:500],
                        'date': updated.strip(),
                        'source': name
                    })
        
        print(f"  Found {len(articles)} articles")
    except ET.ParseError as e:
        print(f"  Warning: Failed to parse feed {name}: {e}")
    
    return articles


def fetch_all_news() -> dict:
    """Fetch news from all RSS feeds."""
    cache_dir = ensure_cache_dir()
    
    all_news = {}
    for name, url in RSS_FEEDS.items():
        articles = fetch_rss_feed(name, url)
        all_news[name] = articles
        
        # Cache the news
        safe_name = re.sub(r'[^\w\-]', '_', name)
        cache_path = cache_dir / f"news_{safe_name}.json"
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
    
    return all_news


def load_cached_news() -> list:
    """Load all cached news articles."""
    cache_dir = get_cache_dir()
    articles = []
    for news_file in cache_dir.glob("news_*.json"):
        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                articles.extend(json.load(f))
        except Exception:
            pass
    return articles


def download_all_pdfs():
    """Download and extract text from all policy PDFs."""
    cache_dir = ensure_cache_dir()
    
    all_pdfs = {**VOLT_EUROPA_PDFS, **VOLT_DEUTSCHLAND_PDFS}
    results = {}
    
    for name, url in all_pdfs.items():
        pdf_path = download_pdf(name, url)
        if pdf_path and pdf_path.exists():
            text = extract_text_from_pdf(pdf_path)
            results[name] = {
                "pdf_path": str(pdf_path),
                "url": url,
                "text_length": len(text),
                "has_text": len(text) > 100
            }
    
    return results


def search_policies(query: str, max_results: int = 10) -> list:
    """Search all cached policy texts for matching content."""
    cache_dir = get_cache_dir()
    results = []
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 3]
    
    for txt_file in cache_dir.glob("*.txt"):
        if txt_file.name.startswith("news_"):
            continue
        
        text = txt_file.read_text(encoding='utf-8', errors='replace')
        text_lower = text.lower()
        
        # Calculate relevance score
        score = 0
        matched_sections = []
        
        # Exact phrase match (highest score)
        if query_lower in text_lower:
            score += 100
            # Find context around match
            idx = text_lower.find(query_lower)
            start = max(0, idx - 200)
            end = min(len(text), idx + len(query) + 200)
            matched_sections.append(text[start:end].strip())
        
        # Word-level matching
        for word in query_words:
            if word in text_lower:
                score += 10
                # Find context
                idx = text_lower.find(word)
                start = max(0, idx - 150)
                end = min(len(text), idx + len(word) + 150)
                matched_sections.append(text[start:end].strip())
        
        if score > 0:
            # Determine source
            source = "Volt Europa" if any(k in txt_file.name for k in ["MOP", "amsterdam", "Amsterdam"]) else "Volt Deutschland"
            
            results.append({
                "document": txt_file.stem.replace("_", " "),
                "source": source,
                "score": score,
                "sections": matched_sections[:3],  # Top 3 matches
                "text_preview": text[:500]
            })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def search_news(query: str, max_results: int = 10) -> list:
    """Search cached news articles for matching content."""
    articles = load_cached_news()
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 3]
    
    results = []
    
    for article in articles:
        title = (article.get('title', '') or '').lower()
        description = (article.get('description', '') or '').lower()
        combined = f"{title} {description}"
        
        score = 0
        
        # Exact phrase match
        if query_lower in combined:
            score += 100
        
        # Word-level matching
        for word in query_words:
            if word in combined:
                score += 10
        
        if score > 0:
            results.append({
                **article,
                "score": score
            })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def verify_citation(citation: str) -> dict:
    """Verify if a specific policy citation exists in the corpus."""
    cache_dir = get_cache_dir()
    citation_lower = citation.lower()
    
    for txt_file in cache_dir.glob("*.txt"):
        if txt_file.name.startswith("news_"):
            continue
        
        text = txt_file.read_text(encoding='utf-8', errors='replace')
        text_lower = text.lower()
        
        if citation_lower in text_lower:
            idx = text_lower.find(citation_lower)
            start = max(0, idx - 300)
            end = min(len(text), idx + len(citation) + 300)
            
            return {
                "found": True,
                "document": txt_file.stem.replace("_", " "),
                "context": text[start:end].strip()
            }
    
    return {"found": False, "message": f"Citation not found: {citation}"}


def check_consistency(statement: str) -> dict:
    """Check if a statement is consistent with Volt policy."""
    policy_results = search_policies(statement)
    news_results = search_news(statement)
    
    analysis = {
        "statement": statement,
        "matches": policy_results,
        "news": news_results[:3],  # Top 3 news matches
        "verdict": "NO_MATCH",
        "confidence": "LOW"
    }
    
    if not policy_results and not news_results:
        return analysis
    
    # Check for contradictions
    contradiction_keywords = ["not", "no", "against", "oppose", "reject", "deny"]
    support_keywords = ["support", "advocate", "promote", "favor", "propose"]
    
    has_contradiction = any(kw in statement.lower() for kw in contradiction_keywords)
    has_support = any(kw in statement.lower() for kw in support_keywords)
    
    if policy_results and policy_results[0]["score"] >= 100:
        # Exact phrase found
        analysis["verdict"] = "MATCH"
        analysis["confidence"] = "HIGH"
    elif policy_results and policy_results[0]["score"] >= 30:
        # Strong word overlap
        if has_contradiction:
            analysis["verdict"] = "POSSIBLE_CONTRADICTION"
            analysis["confidence"] = "MEDIUM"
        elif has_support:
            analysis["verdict"] = "PARTIAL_MATCH"
            analysis["confidence"] = "MEDIUM"
        else:
            analysis["verdict"] = "PARTIAL_MATCH"
            analysis["confidence"] = "MEDIUM"
    elif news_results and news_results[0]["score"] >= 50:
        # News match found
        analysis["verdict"] = "NEWS_REFERENCE"
        analysis["confidence"] = "MEDIUM"
    else:
        # Weak match
        analysis["verdict"] = "THEMATIC_ALIGNMENT"
        analysis["confidence"] = "LOW"
    
    return analysis


def get_cache_status() -> dict:
    """Get status of the PDF cache."""
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    pdfs = list(cache_dir.glob("*.pdf"))
    txts = list(cache_dir.glob("*.txt"))
    news = list(cache_dir.glob("news_*.json"))
    
    total_size = sum(f.stat().st_size for f in cache_dir.iterdir()) if cache_dir.iterdir() else 0
    
    config = load_config()
    
    return {
        "cache_dir": str(cache_dir),
        "source": "github" if "github_repo" in config else "local",
        "github_repo": config.get("github_repo", None),
        "pdf_count": len(pdfs),
        "txt_count": len(txts),
        "news_feeds": len(news),
        "total_size_mb": total_size / (1024 * 1024),
        "last_updated": max(f.stat().st_mtime for f in cache_dir.iterdir()) if cache_dir.iterdir() else None
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python volt_policy_checker.py download       - Download all PDFs")
        print("  python volt_policy_checker.py fetch-news     - Fetch RSS news feeds")
        print("  python volt_policy_checker.py search <query> - Search policies")
        print("  python volt_policy_checker.py search-news <query> - Search news")
        print("  python volt_policy_checker.py check <statement> - Check consistency")
        print("  python volt_policy_checker.py verify <citation> - Verify citation")
        print("  python volt_policy_checker.py status         - Show cache status")
        print("  python volt_policy_checker.py sync           - Pull from GitHub (if configured)")
        print("  python volt_policy_checker.py push [msg]     - Push to GitHub (if configured)")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "download":
        results = download_all_pdfs()
        print(f"\nDownloaded {len(results)} PDFs")
        for name, info in results.items():
            status = "✓" if info["has_text"] else "✗"
            print(f"  {status} {name} ({info['text_length']} chars)")
    
    elif command == "fetch-news":
        all_news = fetch_all_news()
        total = sum(len(articles) for articles in all_news.values())
        print(f"\nFetched {total} news articles")
        for name, articles in all_news.items():
            print(f"  {name}: {len(articles)} articles")
    
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python volt_policy_checker.py search <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        results = search_policies(query)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif command == "search-news":
        if len(sys.argv) < 3:
            print("Usage: python volt_policy_checker.py search-news <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        results = search_news(query)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif command == "check":
        if len(sys.argv) < 3:
            print("Usage: python volt_policy_checker.py check <statement>")
            sys.exit(1)
        statement = " ".join(sys.argv[2:])
        result = check_consistency(statement)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif command == "verify":
        if len(sys.argv) < 3:
            print("Usage: python volt_policy_checker.py verify <citation>")
            sys.exit(1)
        citation = " ".join(sys.argv[2:])
        result = verify_citation(citation)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif command == "status":
        status = get_cache_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    
    elif command == "sync":
        from cache_manager import setup_github_repo, load_config
        config = load_config()
        if 'github_repo' in config:
            setup_github_repo(config['github_repo'])
        else:
            print("No GitHub repo configured. Run: python cache_manager.py setup-github <repo_url>")
    
    elif command == "push":
        from cache_manager import push_to_github
        msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Update Volt policy cache"
        push_to_github(msg)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
