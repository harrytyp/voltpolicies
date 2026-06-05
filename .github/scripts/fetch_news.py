#!/usr/bin/env python3
"""
Fetch Volt news from multiple sources:
1. RSS feeds (20 items each)
2. Mastodon API (all posts)
3. Volt website scraping (all articles)
"""

import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
from html import unescape

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"


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
        # Find account ID
        r = subprocess.run(
            ["curl", "-sL", f"https://mastodon.social/api/v1/accounts/lookup?acct={username}"],
            capture_output=True, text=True, timeout=30
        )
        account = json.loads(r.stdout)
        account_id = account.get('id')
        total = account.get('statuses_count', 0)
        print(f"    Account ID: {account_id}, Total posts: {total}")
        
        # Fetch all posts with pagination
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
                # Extract links from HTML content
                links = re.findall(r'href="(https?://[^"]+)"', content)
                text_clean = re.sub(r'<[^>]+>', '', content).strip()
                
                all_posts.append({
                    'title': text_clean[:100],
                    'link': post.get('url', ''),
                    'description': text_clean[:500],
                    'date': post.get('created_at', ''),
                    'source': f'Volt in the Press (Mastodon)',
                    'via': 'mastodon_api',
                    'external_links': links[:3]
                })
            
            max_id = data[-1]['id']
            
            if len(data) < 40:
                break
        
        print(f"    → {len(all_posts)} posts fetched")
        return all_posts
    except Exception as e:
        print(f"    → Error: {e}")
        return []


def fetch_volt_website(name: str, url: str) -> list:
    """Scrape news articles from Volt website."""
    print(f"  Website: {name}...")
    
    try:
        import subprocess
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result.stdout, 'html.parser')
        
        articles = []
        seen = set()
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            title = a.get_text(strip=True)
            
            # Filter for news articles
            if title and len(title) > 15 and ('/neuigkeiten/' in href or '/news/' in href):
                if not href.startswith('http'):
                    href = f"https://{url.split('//')[1].split('/')[0]}{href}"
                
                if href not in seen:
                    seen.add(href)
                    articles.append({
                        'title': title[:200],
                        'link': href,
                        'description': '',
                        'date': '',
                        'source': name,
                        'via': 'website_scrape'
                    })
        
        print(f"    → {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"    → Error: {e}")
        return []


def fetch_all_news() -> dict:
    """Fetch news from all sources."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    all_news = {}
    
    # 1. RSS feeds (quick, 20 items each)
    print("Fetching RSS feeds...")
    rss_feeds = {
        "Volt Deutschland News": "https://voltdeutschland.org/neuigkeiten/rss",
        "Volt Europa News": "https://volteuropa.org/news/rss",
    }
    for name, url in rss_feeds.items():
        articles = fetch_rss_feed(name, url)
        all_news[name] = articles
    
    # 2. Mastodon API (all posts)
    print("\nFetching Mastodon posts...")
    mastodon_posts = fetch_mastodon_all("voltinthepress")
    all_news["Volt in the Press (Mastodon)"] = mastodon_posts
    
    # 3. Volt website scraping
    print("\nScraping Volt websites...")
    de_articles = fetch_volt_website("Volt Deutschland", "https://voltdeutschland.org/neuigkeiten")
    eu_articles = fetch_volt_website("Volt Europa", "https://volteuropa.org/news")
    
    # Merge website articles into RSS sources
    all_news.setdefault("Volt Deutschland News", []).extend(de_articles)
    all_news.setdefault("Volt Europa News", []).extend(eu_articles)
    
    # Deduplicate all sources
    for source in all_news:
        seen = set()
        unique = []
        for article in all_news[source]:
            key = article.get('link', article.get('title', ''))
            if key not in seen:
                seen.add(key)
                unique.append(article)
        all_news[source] = unique
    
    # Save to cache
    total = 0
    for name, articles in all_news.items():
        safe_name = re.sub(r'[^\w\-]', '_', name)
        cache_path = CACHE_DIR / f"news_{safe_name}.json"
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        total += len(articles)
        print(f"  {name}: {len(articles)} articles saved")
    
    print(f"\nTotal: {total} articles")
    return all_news


if __name__ == "__main__":
    fetch_all_news()
