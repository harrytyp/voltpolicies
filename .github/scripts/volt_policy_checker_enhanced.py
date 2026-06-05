#!/usr/bin/env python3
"""
Enhanced Volt Policy Checker with page numbers and URLs.
Extends the base volt_policy_checker.py with richer metadata.
"""

import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

# Import base functions
import sys
sys.path.insert(0, str(Path(__file__).parent))
from volt_policy_checker import (
    VOLT_EUROPA_PDFS, VOLT_DEUTSCHLAND_PDFS, RSS_FEEDS,
    get_cache_dir, load_config
)

# Document name → URL mapping
DOC_URLS = {}
for name, url in {**VOLT_EUROPA_PDFS, **VOLT_DEUTSCHLAND_PDFS}.items():
    safe_name = re.sub(r'[^\w\-]', '_', name)
    DOC_URLS[safe_name] = url

# RSS feed URL mapping (populated after fetch)
NEWS_URLS = {}


def extract_text_with_pages(pdf_path: Path) -> list:
    """Extract text from PDF with page numbers.
    
    Returns list of {"page": int, "text": str} dicts.
    """
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append({"page": i + 1, "text": text})
        doc.close()
        return pages
    except Exception as e:
        print(f"  Error extracting {pdf_path.name}: {e}")
        return []


def extract_text_with_pages_to_file(pdf_path: Path) -> str:
    """Extract text with pages and save to JSON metadata file."""
    cache_dir = get_cache_dir()
    
    # Check if metadata already exists
    meta_path = cache_dir / f"{pdf_path.stem}_meta.json"
    txt_path = cache_dir / f"{pdf_path.stem}.txt"
    
    if meta_path.exists():
        return txt_path.read_text(encoding='utf-8', errors='replace') if txt_path.exists() else ""
    
    pages = extract_text_with_pages(pdf_path)
    
    # Save metadata
    meta = {
        "document": pdf_path.stem.replace("_", " "),
        "url": DOC_URLS.get(pdf_path.stem, ""),
        "pages": pages
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    
    # Save combined text (for backward compatibility)
    combined = "\n\n".join(p["text"] for p in pages)
    txt_path.write_text(combined, encoding='utf-8')
    
    return combined


def search_policies_enhanced(query: str, max_results: int = 10) -> list:
    """Enhanced search with page numbers, URLs, and section headings."""
    cache_dir = get_cache_dir()
    results = []
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 3]
    
    for meta_file in cache_dir.glob("*_meta.json"):
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        
        doc_name = meta.get("document", meta_file.stem.replace("_meta", "").replace("_", " "))
        doc_url = meta.get("url", "")
        
        for page_data in meta.get("pages", []):
            page_num = page_data["page"]
            text = page_data["text"]
            text_lower = text.lower()
            
            score = 0
            matched_sections = []
            
            # Exact phrase match
            if query_lower in text_lower:
                score += 100
                idx = text_lower.find(query_lower)
                start = max(0, idx - 200)
                end = min(len(text), idx + len(query) + 200)
                section = text[start:end].strip()
                matched_sections.append({
                    "text": section,
                    "page": page_num,
                    "offset": idx
                })
            
            # Word-level matching
            for word in query_words:
                if word in text_lower:
                    score += 10
                    idx = text_lower.find(word)
                    start = max(0, idx - 150)
                    end = min(len(text), idx + len(word) + 150)
                    section = text[start:end].strip()
                    if not any(s["text"] == section for s in matched_sections):
                        matched_sections.append({
                            "text": section,
                            "page": page_num,
                            "offset": idx
                        })
            
            if score > 0:
                # Try to extract section heading
                heading = extract_heading(text, matched_sections[0]["offset"] if matched_sections else 0)
                
                source = "Volt Europa" if any(k in meta_file.name for k in ["MOP", "amsterdam", "Amsterdam"]) else "Volt Deutschland"
                
                results.append({
                    "document": doc_name,
                    "source": source,
                    "url": doc_url,
                    "page": page_num,
                    "section_heading": heading,
                    "score": score,
                    "sections": [s["text"] for s in matched_sections[:2]],
                    "text_preview": text[:500]
                })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Deduplicate by document + page
    seen = set()
    unique = []
    for r in results:
        key = f"{r['document']}:{r['page']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    
    return unique[:max_results]


def extract_heading(text: str, offset: int) -> str:
    """Try to extract the section heading before the match."""
    # Look backwards from offset for a heading-like line
    lines = text[:offset].split('\n')
    for line in reversed(lines[-10:]):
        line = line.strip()
        if not line:
            continue
        # Heading patterns: starts with number, all caps, or short line
        if len(line) < 100 and (
            line.startswith(('I.', 'II.', 'III.', 'IV.', 'V.', 'VI.', 'VII.', 'VIII.', 'IX.', 'X.')) or
            line.isupper() or
            re.match(r'^\d+[\.\)]', line) or
            re.match(r'^[A-Z][a-z]+(\s[A-Z][a-z]+)*$', line)
        ):
            return line
    return ""


def search_news_enhanced(query: str, max_results: int = 10) -> list:
    """Enhanced news search with direct article URLs."""
    from volt_policy_checker import load_cached_news
    articles = load_cached_news()
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 3]
    
    results = []
    
    for article in articles:
        title = (article.get('title', '') or '').lower()
        description = (article.get('description', '') or '').lower()
        link = article.get('link', '')
        combined = f"{title} {description}"
        
        score = 0
        
        if query_lower in combined:
            score += 100
        
        for word in query_words:
            if word in combined:
                score += 10
        
        if score > 0:
            # Clean description (remove HTML)
            desc_clean = re.sub(r'<[^>]+>', '', article.get('description', ''))
            desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()[:300]
            
            results.append({
                "title": article.get('title', ''),
                "url": link,
                "date": article.get('date', ''),
                "source": article.get('source', ''),
                "description": desc_clean,
                "score": score
            })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python volt_policy_checker_enhanced.py search <query>")
        print("  python volt_policy_checker_enhanced.py search-news <query>")
        print("  python volt_policy_checker_enhanced.py reindex")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "reindex":
        # Re-extract all PDFs with page metadata
        cache_dir = get_cache_dir()
        pdfs = list(cache_dir.glob("*.pdf"))
        print(f"Re-indexing {len(pdfs)} PDFs with page metadata...")
        for pdf in pdfs:
            print(f"  {pdf.name}...")
            extract_text_with_pages_to_file(pdf)
        print("Done!")
    
    elif command == "search":
        query = " ".join(sys.argv[2:])
        results = search_policies_enhanced(query)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif command == "search-news":
        query = " ".join(sys.argv[2:])
        results = search_news_enhanced(query)
        print(json.dumps(results, indent=2, ensure_ascii=False))
