#!/usr/bin/env python3
"""Download and extract PDFs from AT and ES Volt chapters."""
import json, subprocess, sys
from pathlib import Path

CACHE_DIR = Path("/opt/data/voltpolicies/cache")
KNOWN_PDFS = Path("/opt/data/voltpolicies/known_pdfs.json")

pdfs = {
    "volt-wahlprogramm-europawahl-2024": ("https://voltoesterreich.org/storage/pdf/volt-wahlprogramm-europawahl-2024.pdf", "Volt Österreich"),
    "volt_eur_electoral_moonshot_programme_2024-29": ("https://voltoesterreich.org/storage/pdf/volt_eur_electoral_moonshot_programme_2024-29.pdf", "Volt Österreich"),
    "volt-spanien-programa-electoral-2023": ("https://voltespana.org/storage/pdf/programaelectoralespana2023/programaelectoral2023.pdf", "Volt Spanien"),
    "volt-spanien-equilibrio-global": ("https://voltespana.org/storage/pdf/programaelectoralespana2023/4_equilibrio_global.pdf", "Volt Spanien"),
}

known = json.loads(KNOWN_PDFS.read_text()) if KNOWN_PDFS.exists() else {"pdfs": {}}

import fitz

for name, (url, source) in pdfs.items():
    if url in known.get("pdfs", {}):
        print(f"SKIP {name}: already in known_pdfs")
        continue

    pdf_path = CACHE_DIR / f"{name}.pdf"
    
    # Download
    print(f"\nDownloading {name}...")
    r = subprocess.run(["curl", "-sL", "-o", str(pdf_path), url], capture_output=True, text=True, timeout=60)
    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        print(f"  FAILED: {r.stderr}")
        continue
    
    size = pdf_path.stat().st_size
    print(f"  Downloaded: {size/1024:.0f} KB")
    
    # Extract
    print(f"  Extracting text...")
    doc = fitz.open(str(pdf_path))
    pages = []
    full_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append({"page": i+1, "text": text})
        full_text.append(text)
    doc.close()
    
    # Save .txt
    txt_path = CACHE_DIR / f"{name}.txt"
    txt_path.write_text("\n\n".join(full_text), encoding='utf-8')
    
    # Save _meta.json
    meta = {
        "document": name,
        "url": url,
        "pages": pages,
        "total_pages": len(pages),
        "total_chars": sum(len(p["text"]) for p in pages),
    }
    meta_path = CACHE_DIR / f"{name}_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    
    total_chars = sum(len(p["text"]) for p in pages)
    print(f"  Extracted {len(pages)} pages, {total_chars} chars")
    
    # Add to known_pdfs
    known.setdefault("pdfs", {})[url] = {"name": name, "source": source}

# Save
KNOWN_PDFS.write_text(json.dumps(known, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"\nDone! Processed {len(pdfs)} PDFs")
