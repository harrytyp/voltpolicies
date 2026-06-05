#!/usr/bin/env python3
"""
Fetch Volt news from multiple sources:
1. RSS feeds (20 items each)
2. Mastodon API (all posts)
3. Volt website scraping (all articles + category pages)
Only processes NEW articles (skips existing).
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from html import unescape

sys.path.insert(0, str(Path(__file__).parent))
from cache_manager import get_cache_dir

CACHE_DIR = None


def fetch_rss_feed(name: str, url: str) -> list:
    """Fetch RSS feed."""
    print(f"  RSS: {name}...")
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return []
        
        root = ET.fromstring(result.stdout)
        articles = []
        
        for item in root.findall('.//item'):
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            description = unescape(item.findtext('description', ''))
            pub_date = item.findtext('pubDate', '')
            
            if title or link:
                articles.append({
                    'title': title.strip(),
                    'link': link.strip(),
                    'description': re.sub(r'<[^>]+>', '', description).strip()[:500],
                    'date': pub_date.strip(),
                    'source': name,
                    'via': 'rss'
                })
        
        print(f"    → {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"    → Error: {e}")
        return []


def fetch_mastodon_all(username: str = "voltinthepress") -> list:
    """Fetch ALL Mastodon posts via API."""
    print(f"  Mastodon API: @{username}...")
    
    try:
        r = subprocess.run(
            ["curl", "-sL", f"https://mastodon.social/api/v1/accounts/lookup?acct={username}"],
            capture_output=True, text=True, timeout=30
        )
        account = json.loads(r.stdout)
        account_id = account.get('id')
        print(f"    Account ID: {account_id}")
        
        all_posts = []
        max_id = None
        
        while True:
            url = f"https://mastodon.social/api/v1/accounts/{account_id}/statuses"
            if max_id:
                url += f"?max_id={max_id}&limit=40"
            else:
                url += "?limit=40"
            
            r = subprocess.run(
                ["curl", "-sL", url],
                capture_output=True, text=True, timeout=30
            )
            data = json.loads(r.stdout)
            
            if not data:
                break
            
            for post in data:
                content = post.get('content', '')
                links = re.findall(r'href="(https?://[^"]+)"', content)
                text_clean = re.sub(r'<[^>]+>', '', content).strip()
                
                all_posts.append({
                    'title': text_clean[:100],
                    'link': post.get('url', ''),
                    'description': text_clean[:500],
                    'date': post.get('created_at', ''),
                    'source': 'Volt in the Press (Mastodon)',
                    'via': 'mastodon_api',
                    'external_links': links[:3]
                })
            
            max_id = data[-1]['id']
            if len(data) < 40:
                break
        
        print(f"    → {len(all_posts)} posts")
        return all_posts
    except Exception as e:
        print(f"    → Error: {e}")
        return []


def scrape_volt_articles(name: str, base_url: str, paths: list) -> list:
    """Scrape articles from Volt website."""
    print(f"  Scraping: {name}...")
    all_articles = []
    seen = set()
    
    for path in paths:
        url = base_url.rstrip('/') + path
        try:
            r = subprocess.run(
                ["curl", "-sL", url],
                capture_output=True, text=True, timeout=30
            )
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.stdout, 'html.parser')
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                
                if not text or len(text) < 15:
                    continue
                
                # Match article patterns
                is_article = False
                if '/neuigkeiten/' in href and href != '/neuigkeiten' and '?' not in href:
                    is_article = True
                elif '/news/' in href and href != '/news' and '?' not in href:
                    is_article = True
                
                if is_article:
                    if not href.startswith('http'):
                        href = base_url.rstrip('/') + ('/' if not href.startswith('/') else '') + href
                    
                    if href not in seen:
                        seen.add(href)
                        all_articles.append({
                            'title': text[:200],
                            'link': href,
                            'description': '',
                            'date': '',
                            'source': name,
                            'via': 'website_scrape'
                        })
        except Exception as e:
            print(f"    Error scraping {url}: {e}")
    
    print(f"    → {len(all_articles)} articles")
    return all_articles


def load_existing_articles(source_name: str) -> set:
    """Load existing article links to avoid re-processing."""
    if not CACHE_DIR:
        return set()
    
    safe_name = re.sub(r'[^\w\-]', '_', source_name)
    cache_path = CACHE_DIR / f"news_{safe_name}.json"
    
    if cache_path.exists():
        with open(cache_path, 'r', encoding='utf-8') as f:
            articles = json.load(f)
        return {a.get('link', '') for a in articles}
    return set()


def save_articles(source_name: str, articles: list):
    """Save articles to cache."""
    if not CACHE_DIR:
        return
    
    safe_name = re.sub(r'[^\w\-]', '_', source_name)
    cache_path = CACHE_DIR / f"news_{safe_name}.json"
    
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)


def merge_and_deduplicate(existing: list, new: list) -> list:
    """Merge existing and new articles, deduplicate by link."""
    seen = set()
    result = []
    
    # Existing first (preserve order)
    for a in existing:
        link = a.get('link', '')
        if link and link not in seen:
            seen.add(link)
            result.append(a)
    
    # New articles (add only if not already present)
    added = 0
    for a in new:
        link = a.get('link', '')
        if link and link not in seen:
            seen.add(link)
            result.append(a)
            added += 1
    
    if added > 0:
        print(f"    + {added} new articles")
    
    return result


def fetch_all_news() -> dict:
    """Fetch news from all sources."""
    global CACHE_DIR
    CACHE_DIR = get_cache_dir()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    all_news = {}
    
    # 1. Volt Deutschland
    print("\n=== Volt Deutschland ===")
    de_rss = fetch_rss_feed("Volt Deutschland RSS", "https://voltdeutschland.org/neuigkeiten/rss")
    de_scrape = scrape_volt_articles(
        "Volt Deutschland",
        "https://voltdeutschland.org",
        ["/neuigkeiten", "/neuigkeiten?category=pressemitteilungen"]
    )
    existing_de = load_existing_articles("Volt Deutschland News")
    merged_de = merge_and_deduplicate(
        [{'title': '', 'link': l, 'description': '', 'date': '', 'source': 'Volt Deutschland News', 'via': 'existing'} for l in existing_de if l],
        de_rss + de_scrape
    )
    all_news["Volt Deutschland News"] = merged_de
    
    # 2. Volt Europa
    print("\n=== Volt Europa ===")
    eu_rss = fetch_rss_feed("Volt Europa RSS", "https://volteuropa.org/news/rss")
    eu_scrape = scrape_volt_articles(
        "Volt Europa",
        "https://volteuropa.org",
        ["/news", "/news?category=press-releases"]
    )
    existing_eu = load_existing_articles("Volt Europa News")
    merged_eu = merge_and_deduplicate(
        [{'title': '', 'link': l, 'description': '', 'date': '', 'source': 'Volt Europa News', 'via': 'existing'} for l in existing_eu if l],
        eu_rss + eu_scrape
    )
    all_news["Volt Europa News"] = merged_eu
    
    # 3. Mastodon
    print("\n=== Mastodon ===")
    mastodon = fetch_mastodon_all("voltinthepress")
    existing_mastodon = load_existing_articles("Volt in the Press  Mastodon")
    merged_mastodon = merge_and_deduplicate(existing_mastodon, mastodon)
    all_news["Volt in the Press (Mastodon)"] = merged_mastodon
    
    # Save all
    print("\n=== Saving ===")
    total = 0
    for name, articles in all_news.items():
        save_articles(name, articles)
        count = len(articles)
        total += count
        print(f"  {name}: {count} articles")
    
    print(f"\nTotal: {total} articles")
    return all_news


if __name__ == "__main__":
    fetch_all_news()
