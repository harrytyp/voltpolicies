#!/usr/bin/env python3
"""One-time: regenerate _meta.json for ALL existing PDFs in known_pdfs.json."""
import json, subprocess, re, sys, time
from pathlib import Path

CACHE = Path(__file__).parent.parent.parent / "cache"
KNOWN = CACHE.parent / "known_pdfs.json"

# Load known PDFs
known = json.loads(KNOWN.read_text())
pdfs_dict = {}
if isinstance(known, dict) and "pdfs" in known:
    for url, info in known["pdfs"].items():
        if isinstance(info, dict):
            pdfs_dict[info.get("name", url)] = url
elif isinstance(known, list):
    for item in known:
        if isinstance(item, dict) and "url" in item:
            pdfs_dict[item.get("name", str(item["url"]))] = item["url"]

print(f"Found {len(pdfs_dict)} known PDFs")

for name, url in sorted(pdfs_dict.items()):
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
