#!/usr/bin/env python3
"""One-time: regenerate _meta.json for ALL existing PDFs in known_pdfs.json."""
import json, subprocess, re, sys, time
from pathlib import Path

CACHE = Path(__file__).parent.parent.parent / "cache"
KNOWN = CACHE.parent / "known_pdfs.json"

# Load known PDFs
known = json.loads(KNOWN.read_text())
if isinstance(known, list):
    items = known
elif isinstance(known, dict):
    items = known.get("pdfs", known)
    if isinstance(items, dict):
        items = items.values()
else:
    items = []

pdf_urls = {}
for item in items:
    if isinstance(item, dict):
        n = item.get("name", "")
        u = item.get("url", "")
        if u: pdf_urls[n] = u

print(f"Found {len(pdf_urls)} known PDFs")

for name, url in sorted(pdf_urls.items()):
    safe = re.sub(r'[^\w\-]', '_', name)
    meta = CACHE / f"{safe}_meta.json"
    pdf = CACHE / f"{safe}.pdf"
    
    if meta.exists():
        print(f"  ✓ {name} (meta exists)")
        continue
    
    print(f"  → Downloading {name}...")
    try:
        subprocess.run(["curl", "-sL", "-o", str(pdf), url], capture_output=True, timeout=60)
        if pdf.exists() and pdf.stat().st_size > 1000:
            # Extract with pages
            import fitz
            doc = fitz.open(str(pdf))
            pages = []
            for i, page in enumerate(doc):
                pages.append({"page": i+1, "text": page.get_text()})
            doc.close()
            
            meta.write_text(json.dumps({"document": name, "url": url, "pages": pages},
                                        indent=2, ensure_ascii=False), encoding="utf-8")
            pdf.unlink()  # Remove PDF (not tracked in git)
            print(f"    ✓ {len(pages)} pages -> {safe}_meta.json")
        else:
            print(f"    ✗ Download failed")
    except Exception as e:
        print(f"    ✗ Error: {e}")
    time.sleep(1)

print("\nDone!")
