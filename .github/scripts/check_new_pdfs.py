#!/usr/bin/env python3
"""
Check for new policy PDFs on Volt websites — also scrapes HTML policy pages.
HTML extraction uses BeautifulSoup for better content quality.
"""
import json, re, subprocess, html
from pathlib import Path
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
    HAS_SOUP = True
except ImportError:
    HAS_SOUP = False

# Load chapters config
CHAPTERS_CONFIG = Path(__file__).resolve().parent.parent.parent / "scripts" / "chapters.json"
with open(CHAPTERS_CONFIG, 'r', encoding='utf-8') as f:
    _chapters_data = json.load(f)

NATIONAL_POLICY_PAGES = {}
for name, info in _chapters_data.get("chapters", {}).items():
    policy_pages = info.get("policy_pages", [])
    site = info.get("website", "")
    if policy_pages:
        for pp in policy_pages:
            label = f"{name} - {pp}"
            url = site.rstrip('/') + pp
            NATIONAL_POLICY_PAGES[label] = url

POLICY_PAGES = {
    "Volt Europa": "https://volteuropa.org/policies/all-policies",
    "Volt Deutschland Statuten": "https://voltdeutschland.org/programm/programme/statuten-de",
    "Volt Deutschland Wahlprogramme": "https://voltdeutschland.org/programm/programme/wahlprogramme",
}
POLICY_PAGES.update(NATIONAL_POLICY_PAGES)

SKIP_PATTERNS = ["kurzwahlprogramm", "kurzform"]

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
KNOWN_PDFS_FILE = CACHE_DIR.parent / "known_pdfs.json"


def normalize_url(url: str) -> str:
    return html.unescape(url)


def load_known_pdfs() -> dict:
    if KNOWN_PDFS_FILE.exists():
        with open(KNOWN_PDFS_FILE, 'r') as f:
            return json.load(f)
    return {"pdfs": {}, "html_pages": {}}


def save_known_pdfs(known: dict):
    with open(KNOWN_PDFS_FILE, 'w') as f:
        json.dump(known, f, indent=2)


def scrape_pdf_links(url: str) -> list:
    """Scrape a page for PDF links."""
    try:
        result = subprocess.run(["curl", "-sL", url], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        html_content = result.stdout
        pdf_pattern = r'href=["\']([^"\']*\.pdf)["\']'
        matches = re.findall(pdf_pattern, html_content, re.IGNORECASE)
        md_pattern = r'\[([^\]]+)\]\(([^)]*\.pdf)\)'
        md_matches = re.findall(md_pattern, html_content, re.IGNORECASE)
        matches.extend([url for _, url in md_matches])
        seen = set()
        pdfs = []
        for link in matches:
            link = html.unescape(link)
            if not link.startswith('http'):
                link = urljoin(url, link)
            if link not in seen:
                seen.add(link)
                pdfs.append(link)
        return pdfs
    except Exception:
        return []


def find_internal_links(url: str, domain: str) -> list:
    """Find all internal links on a page — prioritized by policy relevance."""
    try:
        result = subprocess.run(["curl", "-sL", url], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        html_content = result.stdout
        links = re.findall(r'href=["\']([^"\']+)["\']', html_content)
        
        policy_keywords = [
            'program', 'beleid', 'standpunt', 'verkiezing', 'overzicht',
            'policy', 'politik', 'politica', 'politique', 'programa',
            'programme', 'manifest', 'thesen', 'position', 'visie',
            'manifesto', 'nuestra', 'initiatief', 'document', 'download'
        ]
        skip_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.svg', 
                          '.webp', '.ico', '.mp4', '.mp3', '.woff', '.woff2', '.ttf']
        skip_paths = ['privacy', 'impressum', 'login', 'register', 'cookie',
                     'datenschutz', 'disclaimer', 'contact', 'press', 'pers',
                     'donate', 'spenden', 'merch', 'shop', 'mitmachen',
                     'vrijwilliger', 'werken-bij', 'spreker']
        
        policy_links = []
        other_links = []
        seen = set()
        
        for link in links:
            link = html.unescape(link)
            if not link.startswith('http'):
                link = urljoin(url, link)
            if domain not in link:
                continue
            if any(ext in link.lower() for ext in skip_extensions):
                continue
            if '#' in link and link.count('/') <= 3:
                continue
            
            link_lower = link.lower()
            if any(s in link_lower for s in skip_paths):
                continue
            
            if link not in seen:
                seen.add(link)
                if any(kw in link_lower for kw in policy_keywords):
                    policy_links.append(link)
                else:
                    other_links.append(link)
        
        # Policy-relevant links first, then others (max 30 total)
        return (policy_links + other_links)[:30]
    except Exception:
        return []


def scrape_pdfs_shallow(url: str, known_pdfs: set) -> list:
    """Scrape a single page for PDF links — no auto-discovery, just the hardcoded URL."""
    direct_pdfs = scrape_pdf_links(url)
    new_direct = [p for p in direct_pdfs if normalize_url(p) not in known_pdfs]
    if new_direct:
        print(f"  PDFs found: {len(new_direct)} new")
    else:
        print(f"  No new PDFs (or this page has no PDF links)")
    return new_direct


def scrape_html_text(url: str) -> tuple[str, str]:
    """Scrape HTML page and extract readable text content.
    Uses BeautifulSoup for clean extraction of main content.
    Returns (title, text).
    """
    try:
        result = subprocess.run(["curl", "-sL", url], capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or len(result.stdout) < 500:
            return ("", "")
        
        html_content = result.stdout
        title = ""
        
        if HAS_SOUP:
            soup = BeautifulSoup(html_content, 'html.parser')
            title_elem = soup.find('title')
            if title_elem:
                title = html.unescape(title_elem.get_text(strip=True))
            
            # Remove unwanted tags
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 
                            'aside', 'form', 'button', 'input', 'select',
                            'noscript', 'svg', 'path', 'img', 'video']):
                tag.decompose()
            
            # Try main content area first
            main = soup.find('main') or soup.find('article') or soup.find('[role="main"]') or soup.find('body')
            if main:
                text = main.get_text(separator='\n')
            else:
                text = soup.get_text(separator='\n')
        else:
            # Fallback: regex extraction
            title_m = re.search(r'<title>(.*?)</title>', html_content)
            title = html.unescape(title_m.group(1).strip()) if title_m else ""
            text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '\n', text)
        
        # Clean up
        text = html.unescape(text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove navigation/short lines
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 30]
        text = '\n\n'.join(lines)
        
        if len(text) < 500:
            return ("", "")
        
        return (title[:100], text[:100000])
    except Exception:
        return ("", "")


def should_skip(url: str) -> bool:
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in SKIP_PATTERNS)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF, save .txt and _meta.json with per-page data."""
    txt_path = CACHE_DIR / f"{pdf_path.stem}.txt"
    meta_path = CACHE_DIR / f"{pdf_path.stem}_meta.json"

    if txt_path.exists() and meta_path.exists():
        return txt_path.read_text(encoding='utf-8', errors='replace')

    try:
        import fitz
        doc = fitz.open(str(pdf_path))

        # Per-page extraction for _meta.json
        pages = []
        full_text_parts = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append({"page": i + 1, "text": text.strip()[:5000]})
                full_text_parts.append(text)
        doc.close()

        if not pages:
            return ""

        # Save .txt (full text)
        full_text = "\n\n".join(full_text_parts)
        txt_path.write_text(full_text, encoding='utf-8')

        # Save _meta.json with per-page data
        doc_name = pdf_path.stem.replace("_", " ").replace("-", " ").strip()
        meta = {
            "document": doc_name,
            "url": "",  # caller should set this if available
            "pages": pages,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

        return full_text
    except ImportError:
        return ""
    except Exception as e:
        print(f"  Warning: Failed to extract text: {e}")
        return ""


def download_pdf(url: str, name: str) -> Path:
    safe_name = re.sub(r'[^\w\-]', '_', name)
    pdf_path = CACHE_DIR / f"{safe_name}.pdf"
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", str(pdf_path), url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 1000:
            return pdf_path
    except Exception:
        pass
    return None


def get_pdf_name(url: str) -> str:
    path = url.split('?')[0].rstrip('/')
    name = path.split('/')[-1].replace('.pdf', '')
    name = name.replace('-', ' ').replace('_', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def get_html_name(url: str, source: str) -> str:
    """Get a readable name for an HTML policy page."""
    # Use the path segments
    path = url.split('?')[0].rstrip('/')
    segments = [s for s in path.split('/') if s and s not in ('programm', 'programme', 'program', 'policies', 'politik', 'politiques', 'programa', 'standpunten', 'politikk')]
    if segments:
        name = ' - '.join(segments[-2:])
    else:
        name = path.split('/')[-1]
    name = name.replace('-', ' ').replace('_', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.title()
    return f"{source} - {name}"


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    known = load_known_pdfs()
    new_pdfs = []
    new_html = []
    
    print("=== Checking for new policy PDFs + HTML pages ===\n")
    
    for source, url in POLICY_PAGES.items():
        print(f"Scraping: {source}")
        known_set = set(known.get("pdfs", {}).keys())
        
        # Shallow scrape the hardcoded policy page URL only — no auto-discovery
        pdf_urls = scrape_pdfs_shallow(url, known_set)
        print(f"  Total new PDFs: {len(pdf_urls)}")
        
        # Process PDFs
        for pdf_url in pdf_urls:
            if should_skip(pdf_url):
                continue
            normalized = normalize_url(pdf_url)
            if normalized in known.get("pdfs", {}):
                continue
            name = get_pdf_name(pdf_url)
            print(f"\n  NEW PDF: {name}")
            pdf_path = download_pdf(pdf_url, name)
            if pdf_path:
                text = extract_text_from_pdf(pdf_path)
                if text:
                    print(f"       ✓ Downloaded and extracted ({len(text)} chars)")
                    new_pdfs.append({"name": name, "url": pdf_url, "source": source, "text_length": len(text)})
                    known.setdefault("pdfs", {})[normalized] = {"name": name, "source": source}
                else:
                    print(f"       ✗ Failed to extract text")
            else:
                print(f"       ✗ Failed to download")
        
        # If no PDFs found on this page, try extracting HTML content
        if not pdf_urls:
            html_url = url
            norm_url = normalize_url(html_url)
            if norm_url not in known.get("html_pages", {}):
                print(f"  Trying HTML extraction...")
                title, text = scrape_html_text(html_url)
                if title and text and len(text) > 500:
                    html_name = get_html_name(html_url, source.split(' - ')[0] if ' - ' in source else source)
                    safe_name = re.sub(r'[^\w\-]', '_', html_name)
                    txt_path = CACHE_DIR / f"{safe_name}.txt"
                    txt_path.write_text(text, encoding='utf-8')
                    print(f"       ✓ Extracted HTML: '{title}' ({len(text)} chars)")
                    new_html.append({"name": html_name, "url": html_url, "source": source, "text_length": len(text)})
                    known.setdefault("html_pages", {})[norm_url] = {"name": html_name, "source": source}
                else:
                    print(f"       - No extractable policy content found")
    
    save_known_pdfs(known)
    
    print(f"\n=== Summary ===")
    print(f"New PDFs downloaded: {len(new_pdfs)}")
    for pdf in new_pdfs:
        print(f"  PDF: {pdf['name']} ({pdf['source']})")
    print(f"New HTML pages scraped: {len(new_html)}")
    for h in new_html:
        print(f"  HTML: {h['name']} ({h['source']})")
    
    return new_pdfs + new_html


if __name__ == "__main__":
    main()
