#!/usr/bin/env python3
"""
Fetch ALL Volt news with pagination.
Sources: RSS + Mastodon API + Website scraping (all pages).
Only adds NEW articles (incremental).

Robustheit: Feed-Antworten werden auf HTTP-Status und Feed-Marker geprueft und
tolerant geparst. Ein Feed, der keine Feed-Antwort liefert (z.B. HTML-404-Seite
oder Bot-Wall) oder dessen XML nicht lesbar ist, wird uebersprungen und am Ende
namentlich im Log aufgelistet - der Lauf bricht dadurch nie ab.
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

# Browser-User-Agent: einige Volt-Seiten liefern ohne UA eine Fehlerseite.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

ATOM_NS = "{http://www.w3.org/2005/Atom}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"

# Uebersprungene Feeds (name, url, grund) - wird am Ende berichtet, damit ein
# fehlender Feed im Log sichtbar ist statt still zu verschwinden.
SKIPPED_FEEDS = []

# HTML-Feeds enthalten oft benannte Entities, die XML nicht kennt (&nbsp;,
# &ndash;, ...) -> ElementTree bricht mit "undefined entity" ab. Ausserdem
# entfernen wir das interne DTD (Billion-Laughs-/XXE-Vektor) und Steuerzeichen.
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*?(\[[^\]]*\])?>", re.S)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ENTITY_RE = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;)([A-Za-z][A-Za-z0-9]*);")
_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}


def http_get(url: str, timeout: int = 30):
    """GET per curl. Liefert (status, body). status == '' bedeutet: curl selbst
    ist gescheitert (Timeout/DNS) - dann steht der Grund im body."""
    try:
        result = subprocess.run(
            ["curl", "-sSL", "--max-time", str(timeout), "-A", UA,
             "-w", "\n__HTTP_STATUS__%{http_code}", url],
            capture_output=True, text=True, timeout=timeout + 20,
        )
    except Exception as e:
        return "", f"curl failed: {e}"

    body, sep, status = result.stdout.rpartition("__HTTP_STATUS__")
    if not sep:
        return "", (result.stderr.strip() or "leere Antwort")[:200]
    return status.strip(), body


def _is_feed(body: str) -> bool:
    head = body[:1000].lstrip()
    return "<rss" in head or "<feed" in head or "<rdf:RDF" in head


def _sanitize_xml(raw: str) -> str:
    """HTML-Feeds ertraeglich machen (DOCTYPE weg, Steuerzeichen weg,
    HTML-Entities -> Unicode). Unbekannte Entities werden zu Text, damit das
    XML auch dann lesbar bleibt."""
    text = _DOCTYPE_RE.sub("", raw)
    text = _CTRL_RE.sub("", text)

    def _entity(m):
        token = m.group(0)
        if m.group(1) in _XML_ENTITIES:
            return token
        decoded = unescape(token)
        return decoded if decoded != token else m.group(1)

    return _ENTITY_RE.sub(_entity, text)


def _parse_feed(raw: str, name: str):
    """Feed-XML tolerant parsen. None, wenn auch die Reparatur scheitert."""
    try:
        return ET.fromstring(raw)
    except ET.ParseError as first:
        try:
            root = ET.fromstring(_sanitize_xml(raw))
        except ET.ParseError:
            return None
        print(f"    ! XML repariert (HTML-Entities entfernt): {first}")
        return root


def _item_text(item, *names: str) -> str:
    for n in names:
        value = item.findtext(n)
        if value:
            return value
    return ""


def _atom_link(item) -> str:
    """Alternate-Link eines Atom-Eintrags."""
    links = item.findall(f"{ATOM_NS}link")
    for link in links:
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href")
    for link in links:
        if link.get("href"):
            return link.get("href")
    return ""


def fetch_rss_feed(name: str, url: str) -> list:
    """RSS- oder Atom-Feed holen. Bricht nie ab: Fehler werden geloggt, der
    Feed wird uebersprungen, der naechste Feed bzw. der Website-Scrape greift."""
    print(f"  RSS: {name} ({url})...")

    status, raw = http_get(url)
    if status == "":
        print(f"    → uebersprungen: {raw[:100]}")
        SKIPPED_FEEDS.append((name, url, raw[:100] or "keine Antwort"))
        return []
    if status != "200":
        print(f"    → uebersprungen: HTTP {status} (kein Feed unter dieser URL)")
        SKIPPED_FEEDS.append((name, url, f"HTTP {status}"))
        return []
    if not _is_feed(raw):
        print(f"    → uebersprungen: keine Feed-Antwort ({len(raw)} Bytes HTML)")
        SKIPPED_FEEDS.append((name, url, f"keine Feed-Antwort ({len(raw)} Bytes HTML)"))
        return []

    root = _parse_feed(raw, name)
    if root is None:
        print("    → uebersprungen: XML nicht lesbar (auch nach Reparatur)")
        SKIPPED_FEEDS.append((name, url, "XML nicht lesbar"))
        return []

    # RSS 2.0 <item>, sonst Atom <entry>
    items = root.findall(".//item") or root.findall(f".//{ATOM_NS}entry")
    articles = []
    for item in items:
        title = _item_text(item, "title", f"{ATOM_NS}title")
        link = _item_text(item, "link", f"{ATOM_NS}id") or _atom_link(item)
        description = _item_text(item, "description", f"{ATOM_NS}summary",
                                 f"{ATOM_NS}content")
        pub_date = _item_text(item, "pubDate", f"{ATOM_NS}published",
                              f"{ATOM_NS}updated", f"{DC_NS}date")

        if title or link:
            articles.append({
                'title': unescape(title).strip(),
                'link': link.strip(),
                'description': re.sub(r'<[^>]+>', '', unescape(description)).strip()[:500],
                'date': pub_date.strip(),
                'source': name,
                'via': 'rss'
            })

    print(f"    → {len(articles)} articles")
    return articles


def fetch_mastodon_all(username: str = "voltinthepress") -> list:
    """Fetch ALL Mastodon posts via API."""
    print(f"  Mastodon API: @{username}...")
    
    try:
        r = subprocess.run(
            [ "curl", "-sL", f"https://mastodon.social/api/v1/accounts/lookup?acct={username}"],
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
    (page has only already-seen links or is empty). Erkennt Artikel-Links am
    konfigurierten News-Pfad (z.B. /news/, /neuigkeiten/, /novyny/).
    """
    print(f"  Scraping: {name} (all pages)...")

    bases = base_url.rstrip('/')
    # Der konfigurierte News-Pfad ist selbst ein Artikel-Praefix (Ukraine
    # z.B. /novyny/) - so werden auch Chapters ohne /news/-URL erfasst.
    patterns = {"/news/", "/neuigkeiten/", path.rstrip('/') + "/"}

    all_articles = []
    seen = set()
    empty_pages = 0
    page = 0

    for page in range(1, 101):  # Safety limit: 100 pages max
        url = f"{bases}{path}?page={page}"
        try:
            status, body = http_get(url)
            if status != "200":
                print(f"    Page {page}: HTTP {status or 'curl-Fehler'} - Ende der Liste")
                break

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, 'html.parser')

            page_articles = 0
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)

                if not text or len(text) < 15:
                    continue

                # Match article patterns
                is_article = any(p in href for p in patterns) and "?" not in href

                if is_article:
                    if not href.startswith('http'):
                        href = bases + ('/' if not href.startswith('/') else '') + href
                    # Listing-Seiten des News-Pfads selbst ausschliessen
                    if href.rstrip('/') in {bases + p.rstrip('/') for p in patterns}:
                        continue

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

    # Fehlende Feeds namentlich berichten (kein stilles Verschlucken)
    if SKIPPED_FEEDS:
        print(f"\n=== Feeds uebersprungen: {len(SKIPPED_FEEDS)} ===")
        for name, url, why in SKIPPED_FEEDS:
            print(f"  - {name}: {url} ({why})")
    else:
        print("\n=== Feeds uebersprungen: 0 ===")

    return all_news


if __name__ == "__main__":
    fetch_all_news()
