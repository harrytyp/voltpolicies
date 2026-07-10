#!/usr/bin/env python3
"""
Fetch ALL Volt news with pagination.
Sources: RSS + Mastodon API + Website scraping (all pages).
Only adds NEW articles (incremental).
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


def scrape_paginated(name: str, base_url: str, path: str) -> list:
    """Scrape all pages of a news section.
    
    Iterates through all pages until no new articles are found
    (page has only already-seen links or is empty).
    """
    print(f"  Scraping: {name} (all pages)...")
    
    all_articles = []
    seen = set()
    empty_pages = 0
    
    for page in range(1, 101):  # Safety limit: 100 pages max
        url = f"{base_url.rstrip('/')}{path}?page={page}"
        try:
            r = subprocess.run(
                ["curl", "-sL", url],
                capture_output=True, text=True, timeout=30
            )
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.stdout, 'html.parser')
            
            page_articles = 0
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
                        page_articles += 1
            
            if page_articles == 0:
                empty_pages += 1
                if empty_pages >= 2:
                    # Two consecutive empty pages = definitely at the end
                    break
            else:
                empty_pages = 0
                
        except Exception as e:
            print(f"    Error on page {page}: {e}")
            break
    
    print(f"    → {len(all_articles)} articles across {page} pages")
    return all_articles


def load_existing(source_name: str) -> list:
    """Load existing articles from cache."""
    if not CACHE_DIR:
        return []
    
    safe_name = re.sub(r'[^\w\-]', '_', source_name)
    cache_path = CACHE_DIR / f"news_{safe_name}.json"
    
    if cache_path.exists():
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_articles(source_name: str, articles: list):
    """Save articles to cache."""
    if not CACHE_DIR:
        return
    
    safe_name = re.sub(r'[^\w\-]', '_', source_name)
    cache_path = CACHE_DIR / f"news_{safe_name}.json"
    
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)


def merge_incremental(existing: list, new: list) -> list:
    """Merge existing and new articles, keeping existing order."""
    seen = {a.get('link', '') for a in existing if a.get('link')}
    result = list(existing)
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

    # Load chapters config
    chapters_path = Path(__file__).parent.parent.parent / "scripts" / "chapters.json"
    with open(chapters_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    chapters = config.get("chapters", {})

    # 1. Volt Europa (pan-European - RSS + paginated scraping)
    print("\n=== Volt Europa ===")
    eu_rss = fetch_rss_feed("Volt Europa RSS", "https://volteuropa.org/news/rss")
    eu_paginated = scrape_paginated("Volt Europa", "https://volteuropa.org", "/news")
    existing_eu = load_existing("Volt Europa News")
    all_news["Volt Europa News"] = merge_incremental(existing_eu, eu_rss + eu_paginated)

    # 2. National chapters (RSS feeds)
    for name, info in sorted(chapters.items()):
        site = info.get("website", "")
        feeds = info.get("rss_feeds", [])
        news_path = info.get("news_path", "/news")
        lang = info.get("news_lang", "en")
        cache_name = f"{name} News"

        print(f"\n=== {name} ===")

        # Try RSS feeds
        all_articles = []
        feeds_active = False
        for feed_path in feeds:
            feed_url = site.rstrip('/') + feed_path
            articles = fetch_rss_feed(f"{name} RSS", feed_url)
            all_articles.extend(articles)
            if articles:
                print(f"    ✓ RSS active: {feed_path}")
                feeds_active = True
                break

        # Always supplement with website scraping (catches articles
        # that appear on the news listing page but NOT in the RSS feed,
        # e.g. manually published pieces, special statements).
        print(f"  Supplementing: {name} (website scrape)...")
        scraped = scrape_paginated(name, site, news_path)
        all_articles.extend(scraped)
        if scraped and not feeds_active:
            print(f"    ✓ Website scrape active (RSS was unavailable): {news_path}")
        elif scraped:
            print(f"    ✓ RSS supplemented with {len(scraped)} website articles")

        existing = load_existing(cache_name)
        all_news[cache_name] = merge_incremental(existing, all_articles)

    # 3. Mastodon (all posts via API)
    print("\n=== Mastodon ===")
    mastodon = fetch_mastodon_all("voltinthepress")
    existing_mastodon = load_existing("Volt in the Press  Mastodon")
    all_news["Volt in the Press (Mastodon)"] = merge_incremental(existing_mastodon, mastodon)
    
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
