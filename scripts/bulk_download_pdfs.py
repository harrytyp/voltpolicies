#!/usr/bin/env python3
"""Bulk download new PDFs found via search, extract text, create _meta.json."""

import json, re, subprocess, sys, time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
KNOWN_PDFS_FILE = CACHE_DIR.parent / "known_pdfs.json"

# All new PDFs to download (country, url, description)
PDFS = [
    ("AT", "https://voltoesterreich.org/storage/wien/wahlprogramm/2025_02_22_programm-wien-wahl-2025-final-de.pdf",
     "Wahlprogramm Wien 2025"),
    ("AT", "https://voltoesterreich.org/storage/pdf/voltat_finanzordnung_fassung-02.09.2023.pdf",
     "Finanzordnung Volt AT"),
    ("BE", "https://voltbelgium.org/storage/pdf/2024/20240502---nl-federaal.pdf",
     "Federaal Verkiezingsprogramma NL"),
    ("BE", "https://voltbelgium.org/storage/governance_documents/volt-belgium---rules-of-procedure-of-the-association-(15.12.2024).pdf",
     "Rules of Procedure BE"),
    ("BE", "https://voltbelgium.org/storage/governance_documents/volt-belgium---financial-provisions-(15.12.2024).pdf",
     "Financial Provisions BE"),
    ("BE", "https://voltbelgium.org/storage/pdf/mop_voltbelgium_2023.pdf",
     "Mapping of Policies BE 2023"),
    ("BE", "https://voltbelgium.org/storage/pdf/2024/vlaanderen2040_31_10_2023.pdf",
     "Vlaanderen2040 Regionalprogramma"),
    ("BE", "https://voltbelgium.org/storage/regional/oost-vlaanderen/evenementen/2025-10-15-european-defence/how-to-defend-europe.pdf",
     "How to Defend Europe"),
    ("CY", "https://voltcyprus.org/storage/volt-cyprus/volt-cyprus-statute-eng.pdf",
     "Volt Cyprus Statute EN"),
    ("CY", "https://voltcyprus.org/storage/volt-cyprus/old-website/cy_founding_declaration_en-m7vmzvdlqquykpe4.pdf",
     "Cyprus Founding Declaration EN"),
    ("CY", "https://voltcyprus.org/storage/volt-cyprus/old-website/the-economic-vision-of-volt-europa---final-draft-dwxwqaz1l5fp3yx2.pdf",
     "Economic Vision Final Draft"),
    ("DE", "https://voltdeutschland.org/storage/assets-de/pdf/eur-pass/englisch_-how-to-vote-in-germany-as-non-german-eur-citizen.pdf",
     "How to Vote in Germany EN"),
    ("ES", "https://voltespana.org/storage/pdf/programa_campana_en.pdf",
     "Programa Campaña EN"),
    ("EU", "https://volteuropa.org/storage/officials-handbook.pdf",
     "Officials Handbook"),
    ("EU", "https://volteuropa.org/storage/exotic-pet-policies.docx.pdf",
     "Exotic Pet Policy"),
    ("EU", "https://volteuropa.org/storage/integrity-syllabus.pdf",
     "Integrity Syllabus"),
    ("EU", "https://volteuropa.org/storage/data-protection-report-2022.pdf",
     "Data Protection Report 2022"),
    ("EU", "https://volteuropa.org/storage/pdf/audit_financial_data_protection_reports/2020_volt_europa-data_protection_report.pdf",
     "Data Protection Report 2020"),
    ("EU", "https://volteuropa.org/storage/data-protection-report-2021.pdf",
     "Data Protection Report 2021"),
    ("FR", "https://voltfrance.org/storage/pdf/programmeete20243mb.pdf",
     "Programme ETE 2024"),
    ("GB", "https://voltuk.org/storage/pdf/2024/volt-uk-constitution.pdf",
     "UK Constitution"),
    ("GB", "https://voltuk.org/storage/pdf/2024/volt-uk-manifesto-general-election.pdf",
     "UK General Election Manifesto 2024"),
    ("LU", "https://voltluxembourg.org/storage/pdf/ecp-own-design-en.pdf",
     "European Campaign Programme EN"),
    ("MT", "https://voltmalta.org/storage/files/volt-malta-manifesto-2022.pdf",
     "Malta Manifesto 2022"),
    ("NL", "https://voltnederland.org/storage/doc/volt_vp_inleiding_english_a4s_v1.pdf",
     "Verkiezingsprogramma Inleiding EN"),
    ("RO", "https://voltromania.org/storage/pdf/cod-etica-conduita.pdf",
     "Cod Etică și Conduită"),
    ("SE", "https://voltsverige.org/storage/pdf/pr_nederlandska-valresultatet.pdf",
     "PR Nederlandska Valresultatet"),
    ("SK", "https://voltslovensko.org/storage/legal/240212-schvalene-stanovy.pdf",
     "Stanovy (Satzung) SK"),
    ("BG", "https://volt.bg/wp-content/uploads/2020/06/%D0%98%D0%BD%D1%84%D0%BE%D1%80%D0%BC%D0%B0%D1%86%D0%B8%D1%8F-%D0%B2%D1%8A%D0%B2-%D0%B2%D1%80%D1%8A%D0%B7%D0%BA%D0%B0-%D1%81-%D1%87%D0%BB.29-%D0%B0%D0%BB.2-%D1%82.1-%D0%BD%D0%B0-%D0%97%D0%9F%D0%9F-%D0%BA%D1%8A%D0%BC-24-%D1%8E%D0%BB%D0%B8-1.pdf",
     "Публичен регистър BG"),
]


def get_pdf_name(url):
    path = url.split('?')[0].rstrip('/')
    name = path.split('/')[-1].replace('.pdf', '')
    name = re.sub(r'[^\w\-]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name


def download_pdf(url, pdf_path):
    result = subprocess.run(
        ["curl", "-sL", "-o", str(pdf_path), url],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 1000:
        return True
    return False


def extract_text_from_pdf(pdf_path):
    """Use pdftotext if available, fall back to python extraction."""
    txt_path = pdf_path.with_suffix('.txt')
    
    # Try pdftotext first
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0 and txt_path.exists() and txt_path.stat().st_size > 100:
        text = txt_path.read_text(encoding='utf-8', errors='replace')
        return text, txt_path
    
    # Fallback: try fitz (PyMuPDF)
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text() + "\n\n"
        doc.close()
        if text.strip():
            txt_path.write_text(text, encoding='utf-8')
            return text, txt_path
    except ImportError:
        pass
    
    return "", None


def create_meta(pdf_path, doc_name, url, pages_text):
    """Create _meta.json for a PDF."""
    pages = []
    for i, page_text in enumerate(pages_text):
        if page_text.strip():
            pages.append({
                "page": i + 1,
                "text": page_text.strip()[:5000]
            })
    
    meta = {
        "document": doc_name,
        "url": url,
        "pages": pages
    }
    
    meta_path = pdf_path.with_name(pdf_path.stem + "_meta.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta_path


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load known PDFs
    known = {"pdfs": {}, "html_pages": {}}
    if KNOWN_PDFS_FILE.exists():
        with open(KNOWN_PDFS_FILE, 'r') as f:
            known = json.load(f)
    
    success = 0
    failed = 0
    
    for country, url, desc in PDFS:
        name = get_pdf_name(url)
        pdf_path = CACHE_DIR / f"{name}.pdf"
        txt_path = CACHE_DIR / f"{name}.txt"
        meta_path = CACHE_DIR / f"{name}_meta.json"
        
        # Skip if already downloaded
        if pdf_path.exists() and meta_path.exists():
            print(f"  [{country}] Bereits vorhanden: {name}")
            known.setdefault("pdfs", {})[url] = {"name": desc, "source": f"Volt {country}"}
            success += 1
            continue
        
        print(f"  [{country}] Downloade: {desc} ({url.split('/')[-1][:40]})...", end=" ", flush=True)
        
        if not download_pdf(url, pdf_path):
            print(f"✗ Download fehlgeschlagen")
            failed += 1
            continue
        
        size = pdf_path.stat().st_size
        print(f"✓ ({size/1024:.0f} KB)", end=" ", flush=True)
        
        # Try to extract per-page text for _meta.json
        pages_text = []
        doc_name = desc
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()
        except ImportError:
            # Fallback: extract full text and treat as single page
            text, _ = extract_text_from_pdf(pdf_path)
            if text:
                pages_text = [text]
        
        if pages_text and any(p.strip() for p in pages_text):
            meta_path = create_meta(pdf_path, doc_name, url, pages_text)
            print(f"meta", end=" ", flush=True)
        
        # Also save flat .txt for backup
        if not txt_path.exists() and pages_text:
            full_text = "\n\n".join(pages_text)
            txt_path.write_text(full_text, encoding='utf-8')
            print(f"txt", end=" ", flush=True)
        
        # Update known_pdfs
        source_name = f"Volt {country}"
        known.setdefault("pdfs", {})[url] = {"name": desc, "source": source_name}
        
        print(f"✓")
        success += 1
        time.sleep(1)  # rate limiting
    
    # Save known_pdfs
    with open(KNOWN_PDFS_FILE, 'w') as f:
        json.dump(known, f, indent=2)
    
    print(f"\n✅ {success} PDFs erfolgreich, {failed} fehlgeschlagen")
    return success > 0


if __name__ == "__main__":
    main()
