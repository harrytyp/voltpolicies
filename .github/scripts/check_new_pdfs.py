#!/usr/bin/env python3
"""
Check for new policy PDFs on Volt Europa and Volt Deutschland websites.
Downloads and extracts text for any new PDFs found.
"""

import json
import re
import subprocess
import html
from pathlib import Path

# Policy pages to scrape
POLICY_PAGES = {
    "Volt Europa": "https://volteuropa.org/policies/all-policies",
    "Volt Deutschland Statuten": "https://voltdeutschland.org/programm/programme/statuten-de",
    "Volt Deutschland Wahlprogramme": "https://voltdeutschland.org/programm/programme/wahlprogramme",
}

# Known PDFs to skip (Kurzwahlprogram variants)
SKIP_PATTERNS = [
    "kurzwahlprogramm",
    "kurzform",
]

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
KNOWN_PDFS_FILE = CACHE_DIR.parent / "known_pdfs.json"


def normalize_url(url: str) -> str:
    """Normalize URL for comparison (decode HTML entities, etc.)."""
    return html.unescape(url)


def load_known_pdfs() -> dict:
    """Load list of previously known PDFs."""
    if KNOWN_PDFS_FILE.exists():
        with open(KNOWN_PDFS_FILE, 'r') as f:
            return json.load(f)
    return {"pdfs": {}}


def save_known_pdfs(known: dict):
    """Save list of known PDFs."""
    with open(KNOWN_PDFS_FILE, 'w') as f:
        json.dump(known, f, indent=2)


def scrape_pdf_links(url: str) -> list:
    """Scrape a page for PDF links."""
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  Failed to fetch {url}")
            return []
        
        html_content = result.stdout
        
        # Find all PDF links
        pdf_pattern = r'href=["\']([^"\']*\.pdf)["\']'
        matches = re.findall(pdf_pattern, html_content, re.IGNORECASE)
        
        # Also look for links in markdown/text format
        md_pattern = r'\[([^\]]+)\]\(([^)]*\.pdf)\)'
        md_matches = re.findall(md_pattern, html_content, re.IGNORECASE)
        matches.extend([url for _, url in md_matches])
        
        # Deduplicate and make absolute URLs
        seen = set()
        pdfs = []
        for link in matches:
            # Normalize HTML entities
            link = html.unescape(link)
            
            if not link.startswith('http'):
                from urllib.parse import urljoin
                link = urljoin(url, link)
            
            if link not in seen:
                seen.add(link)
                pdfs.append(link)
        
        return pdfs
    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return []


def should_skip(url: str) -> bool:
    """Check if this PDF should be skipped."""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in SKIP_PATTERNS)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using pymupdf. Creates .txt AND _meta.json (per-page)."""
    txt_path = CACHE_DIR / f"{pdf_path.stem}.txt"
    meta_path = CACHE_DIR / f"{pdf_path.stem}_meta.json"
    
    if txt_path.exists() and meta_path.exists():
        return txt_path.read_text(encoding='utf-8', errors='replace')
    
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pages_data = []
        full_text = ""
        for i, page in enumerate(doc):
            page_text = page.get_text()
            pages_data.append({"page": i + 1, "text": page_text})
            full_text += page_text + "\n\n"
        doc.close()
        
        txt_path.write_text(full_text, encoding='utf-8')
        
        # Also save per-page metadata
        meta_path.write_text(json.dumps({
            "document": pdf_path.stem.replace("_", " "),
            "url": "",  # filled in by the caller
            "pages": pages_data
        }, indent=2, ensure_ascii=False), encoding='utf-8')
        
        return full_text
    except ImportError:
        print("  Warning: pymupdf not installed")
        return ""
    except Exception as e:
        print(f"  Warning: Failed to extract text: {e}")
        return ""


def download_pdf(url: str, name: str) -> Path:
    """Download a PDF."""
    safe_name = re.sub(r'[^\w\-]', '_', name)
    pdf_path = CACHE_DIR / f"{safe_name}.pdf"
    
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", str(pdf_path), url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 1000:
            return pdf_path
    except Exception as e:
        print(f"  Failed to download: {e}")
    
    return None


def get_pdf_name(url: str) -> str:
    """Extract a readable name from the URL."""
    # Remove URL parameters and get filename
    path = url.split('?')[0].rstrip('/')
    name = path.split('/')[-1].replace('.pdf', '')
    
    # Make it readable
    name = name.replace('-', ' ').replace('_', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


def main():
    """Check for new PDFs and download them."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    known = load_known_pdfs()
    new_pdfs = []
    
    print("=== Checking for new policy PDFs ===\n")
    
    for source, url in POLICY_PAGES.items():
        print(f"Scraping: {source}")
        pdf_urls = scrape_pdf_links(url)
        print(f"  Found {len(pdf_urls)} PDF links")
        
        for pdf_url in pdf_urls:
            if should_skip(pdf_url):
                continue
            
            # Normalize URL for comparison
            normalized = normalize_url(pdf_url)
            
            if normalized in known.get("pdfs", {}):
                continue
            
            # New PDF found!
            name = get_pdf_name(pdf_url)
            print(f"\n  NEW: {name}")
            print(f"       URL: {pdf_url}")
            
            # Download
            pdf_path = download_pdf(pdf_url, name)
            if pdf_path:
                # Extract text
                text = extract_text_from_pdf(pdf_path)
                if text:
                    print(f"       ✓ Downloaded and extracted ({len(text)} chars)")
                    new_pdfs.append({
                        "name": name,
                        "url": pdf_url,
                        "source": source,
                        "text_length": len(text)
                    })
                    known.setdefault("pdfs", {})[normalized] = {
                        "name": name,
                        "source": source
                    }
                else:
                    print(f"       ✗ Failed to extract text")
            else:
                print(f"       ✗ Failed to download")
    
    # Save known PDFs list
    save_known_pdfs(known)
    
    print(f"\n=== Summary ===")
    print(f"New PDFs found: {len(new_pdfs)}")
    for pdf in new_pdfs:
        print(f"  - {pdf['name']} ({pdf['source']})")
    
    return new_pdfs


if __name__ == "__main__":
    main()
