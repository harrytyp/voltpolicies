#!/usr/bin/env python3
"""Check ZIP files against known PDFs to find what's new."""
import json
import os
import zipfile
from pathlib import Path

# Load known PDFs
known_path = Path.home() / 'voltpolicies' / 'known_pdfs.json'
with open(known_path) as f:
    known = json.load(f)

known_urls = set(known.get('pdfs', {}).keys())
known_names = set(info.get('name', '') for info in known.get('pdfs', {}).values())

zips = [
    r"C:\Users\go75bel\Downloads\weitere policies\drive-download-20260612T154733Z-3-001.zip",
    r"C:\Users\go75bel\Downloads\weitere policies\drive-download-20260612T154752Z-3-001.zip",
    r"C:\Users\go75bel\Downloads\weitere policies\Kommunalwahlen-20260612T154727Z-3-001.zip",
]

all_new = []
all_existing = []

for zip_path in zips:
    name = os.path.basename(zip_path)
    print(f"\n{'='*60}")
    print(f"=== {name} ===")
    print('='*60)
    
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            fname = info.filename
            if not fname.lower().endswith('.pdf'):
                continue
            
            short = fname.replace('\\', '/').split('/')[-1]
            basename = os.path.splitext(short)[0]
            is_kurz = 'kurzwahl' in short.lower() or 'ultrakurz' in short.lower()
            
            # Check if this looks like something already in known_pdfs
            # by comparing the "cleaned" name
            clean_name = basename.replace('_', ' ').replace('-', ' ').lower()
            
            already_in = False
            for kn in known_names:
                if basename[:20].lower() in kn.lower() or kn[:20].lower() in basename.lower():
                    already_in = True
                    break
            
            tag = 'KURZ' if is_kurz else 'WAHL' if 'Wahl' in short else 'POSI'
            
            if already_in:
                print(f"  [ALREADY IN] [{tag}] {short}")
                all_existing.append(short)
            elif is_kurz:
                print(f"  [SKIP KURZ] [{tag}] {short}")
            else:
                print(f"  [*** NEW ***] [{tag}] {short}")
                all_new.append(short)

print(f"\n{'='*60}")
print(f"SUMMARY:")
print(f"  Already in corpus: {len(all_existing)}")
print(f"  New and NOT Kurzwahl: {len(all_new)}")
print(f"  Skipped (Kurzwahl): will be skipped")
print(f"\n{'='*60}")
print("NEW FILES TO ADD:")
for f in all_new:
    print(f"  {f}")
