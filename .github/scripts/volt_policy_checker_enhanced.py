#!/usr/bin/env python3
"""
Enhanced Volt Policy Checker with page numbers and URLs.
Extends the base volt_policy_checker.py with richer metadata.
Supports country/chapter filtering.
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
    get_cache_dir, load_config, load_cached_news
)

# Load chapters config
CHAPTERS_CONFIG = Path(__file__).parent.parent.parent / "scripts" / "chapters.json"
CHAPTERS = {}
if CHAPTERS_CONFIG.exists():
    with open(CHAPTERS_CONFIG, 'r', encoding='utf-8') as f:
        CHAPTERS = json.load(f).get("chapters", {})

# Load translation dictionaries for all languages
TRANSLATIONS_CONFIG = Path(__file__).parent.parent.parent / "scripts" / "translations.json"
LANG_DICTS = {}
if TRANSLATIONS_CONFIG.exists():
    with open(TRANSLATIONS_CONFIG, 'r', encoding='utf-8') as f:
        LANG_DICTS = json.load(f)

# Build language → chapter mapping
# Each chapter has one or more languages (from chapters.json 'news_lang')
LANG_TO_CHAPTERS: dict[str, list[str]] = {}
for name, info in CHAPTERS.items():
    lang = info.get("news_lang", "en")
    LANG_TO_CHAPTERS.setdefault(lang, [])
    LANG_TO_CHAPTERS[lang].append(name)
# Volt Europa is in English
LANG_TO_CHAPTERS.setdefault("en", [])

# Build chapter → languages mapping (chapter can have multiple languages)
CHAPTER_TO_LANGS: dict[str, list[str]] = {}
for name, info in CHAPTERS.items():
    lang = info.get("news_lang", "en")
    CHAPTER_TO_LANGS[name] = [lang]
# German chapters also understand EN
# Volt Europa is primarily EN

# Document name → URL mapping
DOC_URLS = {}
for name, url in {**VOLT_EUROPA_PDFS, **VOLT_DEUTSCHLAND_PDFS}.items():
    safe_name = re.sub(r'[^\w\-]', '_', name)
    DOC_URLS[safe_name] = url

# RSS feed URL mapping (populated after fetch)
NEWS_URLS = {}

# ============================================================
# Bilingual keyword expansion (DE ↔ EN)
# ============================================================
DE_EN_DICT = {
    "migrationszentren": "migration centers",
    "migrationszentrum": "migration center",
    "asyl": "asylum",
    "asylverfahren": "asylum procedure asylum procedures",
    "asylsystem": "asylum system",
    "asylpolitik": "asylum policy",
    "asylrecht": "asylum law right to asylum",
    "asylbewerber": "asylum seeker asylum seekers",
    "asylsuchende": "asylum seeker asylum seekers",
    "flüchtling": "refugee refugees",
    "flüchtlinge": "refugees",
    "geflüchtete": "refugees displaced persons",
    "aufnahmezentrum": "reception center reception centres",
    "aufnahmelager": "reception camp",
    "einwanderung": "immigration",
    "zuwanderung": "immigration migration",
    "remigration": "remigration",
    "rückführung": "return deportation repatriation",
    "abschiebung": "deportation",
    "dublin": "dublin regulation dublin iii",
    "grenzkontrollen": "border controls",
    "grenzschutz": "border protection",
    "frontex": "frontex",
    "seenotrettung": "search and rescue sea rescue",
    "migrationspakt": "migration pact",
    "migrationspolitik": "migration policy",
    "migranten": "migrants",
    "schutzsuchende": "people seeking protection",
    "menschenhandel": "human trafficking",
    "geas": "common european asylum system ceas",
    "europäisches asylsystem": "common european asylum system",
    "klima": "climate",
    "klimawandel": "climate change",
    "klimakrise": "climate crisis",
    "klimaneutral": "climate neutral carbon neutral",
    "klimaschutz": "climate protection climate action",
    "europäische union": "european union",
    "eu-reform": "eu reform",
    "föderal": "federal",
    "mitgliedstaat": "member state member states",
    "kommission": "commission european commission",
    "parlament": "parliament",
    "rat der eu": "council of the eu",
    "vertrag": "treaty",
    "grundrechte": "fundamental rights",
    "rechtsstaat": "rule of law",
    "demokratie": "democracy",
    "wirtschaft": "economy economic",
    "steuern": "tax taxes",
    "haushalt": "budget",
    "investition": "investment",
    "binnenmarkt": "single market internal market",
    "digital": "digital",
    "innovation": "innovation",
    "wettbewerb": "competition",
    "sozial": "social",
    "bildung": "education",
    "gesundheit": "health healthcare",
    "rente": "pension pensions",
    "gleichstellung": "equality gender equality",
    "inklusion": "inclusion",
    "armut": "poverty",
    "verteidigung": "defence defense",
    "sicherheit": "security",
    "armee": "army",
    "nato": "nato",
    "außenpolitik": "foreign policy",
    "sanktionen": "sanctions",
    "energie": "energy",
    "erneuerbare": "renewable renewables",
    "atomkraft": "nuclear power nuclear energy",
    "kohle": "coal",
    "wasserstoff": "hydrogen",
    "unterstützen": "support",
    "fördern": "promote support encourage",
    "stärken": "strengthen",
    "schützen": "protect",
    "ablehnen": "reject oppose",
    "fordern": "demand call for",
    "vorschlagen": "propose",
    "einführen": "introduce establish",
    "verbessern": "improve",
    "reform": "reform",
    "zukunft": "future",
    "nachhaltigkeit": "sustainability",
    "transparenz": "transparency",
    "bürger": "citizen citizens",
    "menschenrechte": "human rights",
}

# Reverse mapping: English → Deutsch
EN_DE_DICT = {}
for de_word, en_words in DE_EN_DICT.items():
    for en_word in en_words.split():
        if en_word not in EN_DE_DICT:
            EN_DE_DICT[en_word] = []
        EN_DE_DICT[en_word].append(de_word)


def expand_query(query: str, target_langs: list[str] = None) -> str:
    """Erweitert eine Suchanfrage um Übersetzungen in relevante Sprachen.
    
    Args:
        query: Der Suchbegriff (in beliebiger Sprache)
        target_langs: Liste der Zielsprachen (z.B. ['de', 'fr']).
                      None = alle verfügbaren Sprachen.
                      'en' wird immer hinzugefügt (universal language).
    
    Returns:
        Erweiterte Suchanfrage mit allen relevanten Begriffen
    """
    words = query.lower().split()
    expanded = set(words)
    
    # Always add English terms from the existing DE↔EN dictionary
    # as it contains the most comprehensive vocabulary
    for word in words:
        clean = word.strip(".,!?;:\"'()[]{}")
        if not clean:
            continue
        
        # DE↔EN (existing, comprehensive vocabulary)
        # Only active when German chapters in scope OR no filter (all languages)
        doit_de = True
        if target_langs:
            # Only expand DE↔EN if German chapters are in the filter
            doit_de = any(l in ("de", "deutsch", "german") for l in target_langs) or \
                      any(l.upper() in ("DE", "AT", "CH") for l in target_langs)
        if doit_de:
            if clean in DE_EN_DICT:
                for en in DE_EN_DICT[clean].split():
                    expanded.add(en)
            if clean in EN_DE_DICT:
                for de in EN_DE_DICT[clean]:
                    expanded.add(de)
        
        # Additional language expansions (FR, IT, ES, NL, PL, PT, SV, ...)
        if target_langs:
            # Only expand to specified languages
            for lang in target_langs:
                if lang == "en":
                    continue  # Already handled above
                lang_dict = LANG_DICTS.get(lang.upper(), LANG_DICTS.get(lang, {}))
                # Check if word is in this language's dictionary (native → EN)
                for native, english in lang_dict.items():
                    if clean in native.lower() or native.lower() in clean:
                        for en_word in english.split():
                            expanded.add(en_word)
        else:
            # No filter: expand to ALL languages we have dictionaries for
            for lang_code, lang_dict in LANG_DICTS.items():
                for native, english in lang_dict.items():
                    if clean in native.lower() or native.lower() in clean:
                        for en_word in english.split():
                            expanded.add(en_word)
    
    result = " ".join(sorted(expanded))
    if result != query.lower() and target_langs:
        print(f"  🔍 Query expanded ({','.join(target_langs)}): '{query}' → '{result}'")
    elif result != query.lower():
        print(f"  🔍 Query expanded (all langs): '{query}' → '{result}'")
    return result


def extract_text_with_pages(pdf_path: Path) -> list:
    """Extract text from PDF with page numbers."""
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

    meta_path = cache_dir / f"{pdf_path.stem}_meta.json"
    txt_path = cache_dir / f"{pdf_path.stem}.txt"

    if meta_path.exists():
        return txt_path.read_text(encoding='utf-8', errors='replace') if txt_path.exists() else ""

    pages = extract_text_with_pages(pdf_path)

    meta = {
        "document": pdf_path.stem.replace("_", " "),
        "url": DOC_URLS.get(pdf_path.stem, ""),
        "pages": pages
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)

    combined = "\n\n".join(p["text"] for p in pages)
    txt_path.write_text(combined, encoding='utf-8')
    return combined


def _get_pdf_source(doc_name: str, doc_url: str, meta_file_name: str) -> str:
    """Determine the country source of a PDF document."""
    if 'volteuropa.org' in doc_url:
        return "Volt Europa"
    for name, info in CHAPTERS.items():
        site = info.get("website", "")
        if site and (site.rstrip('/') in doc_url or site.split("//")[-1].split("/")[0] in doc_url):
            return name
    if "MOP" in doc_name or "amsterdam" in doc_name.lower() or "Amsterdam" in doc_name:
        return "Volt Europa"
    return "Volt Deutschland"


def _filter_by_chapters(source: str, chapters: list[str]) -> bool:
    """Check if a source matches the requested chapter filter."""
    if not chapters:
        return True
    for chapter in chapters:
        chapter_lower = chapter.lower().strip()
        source_lower = source.lower()
        # Match "Europa" -> "Volt Europa"
        if chapter_lower in source_lower or source_lower in chapter_lower:
            return True
        # Match country abbreviations like "DE", "FR"
        for name, info in CHAPTERS.items():
            if info.get("country", "").lower() == chapter_lower:
                if name.lower() in source_lower or source_lower in name.lower():
                    return True
    return False


def _get_langs_from_chapters(chapters: list[str] | None) -> list[str] | None:
    """Determine which languages to search based on chapter filter.
    
    Returns None = search all languages.
    Returns list = only search these languages + English.
    """
    if not chapters:
        return None
    
    langs = set()
    for chapter in chapters:
        chapter_lower = chapter.lower().strip()
        
        # EU / Europa → English
        if chapter_lower in ("eu", "europa", "volt europa", "europe"):
            langs.add("en")
            continue
        
        # Country code (e.g. "DE") or full name (e.g. "Volt Österreich")
        for name, info in CHAPTERS.items():
            code = info.get("country", "").lower()
            name_lower = name.lower()
            # Exact code match OR chapter name starts with/equals query
            if chapter_lower == code:
                lang = info.get("news_lang", "en")
                langs.add(lang)
                break
            # Full chapter name match (e.g. "Volt Österreich" matches "Volt Österreich")
            if chapter_lower == name_lower or name_lower.startswith(chapter_lower) or chapter_lower.startswith(name_lower):
                lang = info.get("news_lang", "en")
                langs.add(lang)
                break
    
    # Always include English
    langs.add("en")
    
    return list(langs) if langs else None


def search_policies_enhanced(query: str, max_results: int = 10, chapters: list[str] = None) -> list:
    """Enhanced search with page numbers, URLs, section headings, and chapter filtering."""
    cache_dir = get_cache_dir()
    results = []

    # Determine target languages from chapter filter
    target_langs = _get_langs_from_chapters(chapters)
    # Expand query for relevant languages only
    expanded_query = expand_query(query, target_langs=target_langs)
    query_lower = expanded_query
    query_words = set(w for w in query_lower.split() if len(w) > 3)
    for w in query.lower().split():
        if len(w) > 3:
            query_words.add(w)
    query_words = list(query_words)

    for meta_file in cache_dir.glob("*_meta.json"):
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        doc_name = meta.get("document", meta_file.stem.replace("_meta", "").replace("_", " "))
        doc_url = meta.get("url", "")
        doc_source = _get_pdf_source(doc_name, doc_url, meta_file.name)

        # Filter by chapters
        if chapters and not _filter_by_chapters(doc_source, chapters):
            continue

        for page_data in meta.get("pages", []):
            page_num = page_data["page"]
            text = page_data["text"]
            text_lower = text.lower()

            score = 0
            matched_sections = []

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
                heading = extract_heading(text, matched_sections[0]["offset"] if matched_sections else 0)
                page_url = f"{doc_url}#page={page_num}" if doc_url else ""

                results.append({
                    "document": doc_name,
                    "source": doc_source,
                    "url": page_url,
                    "page": page_num,
                    "section_heading": heading,
                    "score": score,
                    "sections": [s["text"] for s in matched_sections[:2]],
                    "text_preview": text[:500]
                })

    results.sort(key=lambda x: x["score"], reverse=True)

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
    lines = text[:offset].split('\n')
    for line in reversed(lines[-10:]):
        line = line.strip()
        if not line:
            continue
        if len(line) < 100 and (
            line.startswith(('I.', 'II.', 'III.', 'IV.', 'V.', 'VI.', 'VII.', 'VIII.', 'IX.', 'X.')) or
            line.isupper() or
            re.match(r'^\d+[\.\)]', line) or
            re.match(r'^[A-Z][a-z]+(\s[A-Z][a-z]+)*$', line)
        ):
            return line
    return ""


def search_news_enhanced(query: str, max_results: int = 10, chapters: list[str] = None) -> list:
    """Enhanced news search with direct article URLs and chapter filtering."""
    articles = load_cached_news()

    # Determine target languages from chapter filter
    target_langs = _get_langs_from_chapters(chapters)
    # Expand query for relevant languages only
    expanded_query = expand_query(query, target_langs=target_langs)
    query_lower = expanded_query
    query_words = set(w for w in query_lower.split() if len(w) > 3)
    for w in query.lower().split():
        if len(w) > 3:
            query_words.add(w)
    query_words = list(query_words)

    results = []

    for article in articles:
        title = (article.get('title', '') or '').lower()
        description = (article.get('description', '') or '').lower()
        link = article.get('link', '')
        source = article.get('source', '')

        # Filter by chapters
        if chapters and not _filter_by_chapters(source, chapters):
            continue

        combined = f"{title} {description}"

        score = 0
        if query_lower in combined:
            score += 100
        for word in query_words:
            if word in combined:
                score += 10

        if score > 0:
            desc_clean = re.sub(r'<[^>]+>', '', article.get('description', ''))
            desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()[:300]

            results.append({
                "title": article.get('title', ''),
                "url": link,
                "date": article.get('date', ''),
                "source": source,
                "description": desc_clean,
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python volt_policy_checker_enhanced.py search <query> [--chapters C1,C2...]")
        print("  python volt_policy_checker_enhanced.py search-news <query> [--chapters C1,C2...]")
        print("  python volt_policy_checker_enhanced.py reindex")
        print("  python volt_policy_checker_enhanced.py list-chapters")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list-chapters":
        print("Available chapters:\n")
        print("  EU / Europa  — Volt Europa (pan-European)")
        for name in sorted(CHAPTERS.keys()):
            info = CHAPTERS[name]
            print(f"  {info.get('country', '??')}  — {name}")
        print("\nUse --chapters with search/search-news (comma-separated, e.g. --chapters EU,DE,FR)")

    elif command == "reindex":
        cache_dir = get_cache_dir()
        pdfs = list(cache_dir.glob("*.pdf"))
        print(f"Re-indexing {len(pdfs)} PDFs with page metadata...")
        for pdf in pdfs:
            print(f"  {pdf.name}...")
            extract_text_with_pages_to_file(pdf)
        print("Done!")

    elif command == "search":
        chapters = None
        args = sys.argv[2:]
        if "--chapters" in args:
            idx = args.index("--chapters")
            chapters = [c.strip() for c in args[idx + 1].split(",")]
            args = args[:idx]
        query = " ".join(args) if args else ""
        if not query:
            print("Error: query required")
            sys.exit(1)
        results = search_policies_enhanced(query, chapters=chapters)
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif command == "search-news":
        chapters = None
        args = sys.argv[2:]
        if "--chapters" in args:
            idx = args.index("--chapters")
            chapters = [c.strip() for c in args[idx + 1].split(",")]
            args = args[:idx]
        query = " ".join(args) if args else ""
        if not query:
            print("Error: query required")
            sys.exit(1)
        results = search_news_enhanced(query, chapters=chapters)
        print(json.dumps(results, indent=2, ensure_ascii=False))
