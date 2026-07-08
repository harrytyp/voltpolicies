#!/usr/bin/env python3
"""
Bluesky Profile Scraper - Holt ALLE Posts von öffentlichen Profilen
über die öffentliche Bluesky API (kein Login nötig).
"""
import json, subprocess, sys, time, re
from pathlib import Path

BLUESKY_API = "https://public.api.bsky.app/xrpc"

def api_get(url):
    r = subprocess.run(["curl", "-sL", url], capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout)

def fetch_all_posts(actor, max_posts=None):
    """Holt ALLE Posts eines Bluesky-Accounts mit Pagination."""
    print(f"\n=== Bluesky: @{actor} ===")
    all_posts = []
    cursor = None
    page = 0
    
    while True:
        page += 1
        url = f"{BLUESKY_API}/app.bsky.feed.getAuthorFeed?actor={actor}&limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        
        try:
            data = api_get(url)
        except Exception as e:
            print(f"  ⚠️ Fehler: {e}")
            time.sleep(2)
            continue
        
        feed = data.get("feed", [])
        if not feed:
            print(f"  Page {page}: Keine Posts mehr")
            break
        
        for item in feed:
            post = item.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "") or ""
            
            # Link zum Post
            uri = post.get("uri", "")
            cid = post.get("cid", "")
            link = f"https://bsky.app/profile/{actor}/post/{uri.rsplit('/', 1)[-1]}" if '/' in uri else ""
            
            all_posts.append({
                "title": text[:150] if text else "(kein Text)",
                "link": link,
                "description": text[:500] if text else "",
                "date": record.get("createdAt", ""),
                "source": f"Bluesky: @{actor}",
                "via": "bluesky_api"
            })
        
        cursor = data.get("cursor")
        has_more = bool(cursor and len(feed) > 0)
        
        print(f"  Page {page}: {len(feed)} Posts (total: {len(all_posts)}){' → weiter' if has_more else ' → fertig'}")
        
        if max_posts and len(all_posts) >= max_posts:
            print(f"  Limit {max_posts} erreicht")
            break
        
        if not has_more:
            break
        
        time.sleep(0.5)  # Rate limit
    
    print(f"  ✅ {len(all_posts)} Posts von @{actor}")
    return all_posts


if __name__ == "__main__":
    # Bluesky-Handles der Volt-Kanäle
    ACCOUNTS = [
        ("voltdeutschland.org", "Volt Deutschland"),
        ("volteuropa.org", "Volt Europa"),
        ("reiniervanlanschot.volteuropa.org", "Reinier van Lanschot (MEP)"),
        ("annastrolenberg.volteuropa.org", "Anna Strolenberg (MEP)"),
        ("sophieintveld.bsky.social", "Sophie in 't Veld (MEP)"),
    ]
    
    cache_dir = Path("/opt/data/voltpolicies/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    all_total = 0
    for handle, name in ACCOUNTS:
        posts = fetch_all_posts(handle, max_posts=None)
        
        safe_name = f"Bluesky_{handle.replace('.', '_').replace('@', '')}"
        cache_path = cache_dir / f"news_{safe_name}.json"
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        
        print(f"  💾 Gespeichert: {cache_path.name} ({len(posts)} Posts)")
        all_total += len(posts)
    
    print(f"\n📊 Gesamt: {all_total} Posts von {len(ACCOUNTS)} Accounts")
