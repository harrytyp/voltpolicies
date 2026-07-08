#!/usr/bin/env python3
"""
Instagram Profile Scraper - Holt ALLE Posts von öffentlichen Profilen
über die interne Instagram API (kein Login nötig).
"""
import json, subprocess, sys, time, re
from pathlib import Path

HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "-H", "Accept: application/json",
    "-H", "X-IG-App-ID: 936619743392459",
    "-H", "Sec-Fetch-Site: same-origin",
    "-H", "Sec-Fetch-Mode: cors",
    "-H", "Referer: https://www.instagram.com/",
    "-H", "Cookie: ig_nrc=1",
]

def api_get(url):
    r = subprocess.run(["curl", "-sL"] + HEADERS + [url], capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout)

def scrape_profile(username, max_posts=None):
    print(f"\n=== Scraping @{username} ===")
    
    # 1. Get user info + first batch of posts
    data = api_get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}")
    user = data.get("data", {}).get("user", {})
    user_id = user.get("id")
    
    if not user_id:
        print(f"  ❌ Konnte @{username} nicht finden")
        return []
    
    print(f"  ID: {user_id}")
    print(f"  Name: {user.get('full_name')}")
    total_posts = user.get("edge_owner_to_timeline_media", {}).get("count", 0)
    print(f"  Posts: {total_posts}")
    print(f"  Follower: {user.get('edge_followed_by', {}).get('count', 0)}")
    
    if total_posts == 0:
        return []
    
    all_posts = []
    end_cursor = None
    has_next = True
    page = 0
    
    # 2. Paginate through all posts using the feed API
    while has_next:
        page += 1
        url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/?count=50"
        if end_cursor:
            url += f"&max_id={end_cursor}"
        
        try:
            feed = api_get(url)
        except Exception as e:
            print(f"  ⚠️ Fehler auf Page {page}: {e}")
            time.sleep(5)
            continue
        
        items = feed.get("items", [])
        if not items:
            print(f"  Stop auf Page {page} – keine Items mehr")
            break
        
        for item in items:
            code = item.get("code", "")
            caption = ""
            if item.get("caption"):
                caption = item["caption"].get("text", "")
            
            timestamp = item.get("taken_at", 0)
            from datetime import datetime
            date_str = datetime.utcfromtimestamp(timestamp).isoformat() if timestamp else ""
            
            all_posts.append({
                "title": caption[:150] if caption else "",
                "link": f"https://www.instagram.com/p/{code}/",
                "description": caption[:500] if caption else "",
                "date": date_str,
                "source": f"Instagram: @{username}",
                "via": "instagram_api"
            })
        
        # Pagination
        more_available = feed.get("more_available", False)
        end_cursor = feed.get("next_max_id") or feed.get("next_min_id")
        has_next = more_available and end_cursor
        
        print(f"  Page {page}: {len(items)} Posts (total: {len(all_posts)}){' → weiter' if has_next else ' → fertig'}")
        
        if max_posts and len(all_posts) >= max_posts:
            print(f"  Limit von {max_posts} erreicht")
            break
        
        # Rate limiting - Instagram mag schnelle Requests nicht
        time.sleep(1)
    
    print(f"\n  ✅ {len(all_posts)} Posts gescrapt von @{username}")
    return all_posts


if __name__ == "__main__":
    accounts = sys.argv[1:] if len(sys.argv) > 1 else ["voltdeutschland"]
    
    # Cache-Verzeichnis
    from pathlib import Path
    cache_dir = Path("/opt/data/voltpolicies/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    for acc in accounts:
        posts = scrape_profile(acc, max_posts=None)  # Alle Posts
        
        # Save to cache
        safe_name = f"Insta_{acc}"
        cache_path = cache_dir / f"news_{safe_name}.json"
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        
        alt_name = f"Insta_{acc.replace('_', ' ')}"
        print(f"  💾 Gespeichert: {cache_path} ({len(posts)} Posts)")
