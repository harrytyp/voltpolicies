#!/usr/bin/env python3
"""
Fetch Volt Europa and Volt Deutschland RSS feeds.
Used by GitHub Actions to auto-update news.
"""

import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

# RSS Feeds
RSS_FEEDS = {
    "Volt Deutschland News": "https://voltdeutschland.org/neuigkeiten/rss",
    "Volt Europa News": "https://volteuropa.org/news/rss",
    "Volt in the Press (Mastodon)": "https://mastodon.social/@voltinthepress.rss",
}

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"


def fetch_rss_feed(name: str, url: str) -> list:
    """Fetch and parse an RSS feed."""
    print(f"Fetching: {name}...")
    
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  Failed to fetch {name}")
            return []
        feed_content = result.stdout
    except Exception as e:
        print(f"  Failed to fetch {name}: {e}")
        return []
    
    articles = []
    try:
        root = ET.fromstring(feed_content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        # RSS 2.0 format
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
        
        # Atom format
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
        print(f"  Failed to parse feed: {e}")
    
    return articles


def main():
    """Fetch all feeds and save to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    total = 0
    for name, url in RSS_FEEDS.items():
        articles = fetch_rss_feed(name, url)
        total += len(articles)
        
        # Save to cache
        safe_name = re.sub(r'[^\w\-]', '_', name)
        cache_path = CACHE_DIR / f"news_{safe_name}.json"
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
    
    print(f"\nTotal: {total} articles saved to {CACHE_DIR}")


if __name__ == "__main__":
    main()
