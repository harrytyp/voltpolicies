#!/usr/bin/env python3
"""Audit der Volt-Policy-URLs und des Caches.

Prueft:
  1. chapters.json -> policy_pages je Land (HTTP-Status + Fehlerseiten-Erkennung)
  2. known_pdfs.json -> bereits gescrapte PDF-/HTML-URLs
  3. cache/*.txt -> Dokumente, die nur eine 404-/Fehlerseite enthalten

Aufruf:
  python scripts/audit_policy_urls.py            # nur Bericht (Exit 1 bei Problemen)
  python scripts/audit_policy_urls.py --quarantine   # Fehlseiten-Dokumente nach ../archive verschieben
"""
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
import concurrent.futures as cf
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
CHUNKS = CACHE / "chunks.json"
# Fehlerseiten-Muster: "404 Page Not Found", "404 - Page not found", "<title>404 ..."
JUNK_RE = re.compile(
    r"(?:404\s*[-–—]?\s*page\s+not\s+found|page\s+not\s+found\s*[-–—]\s*volt|<title>\s*404|\b404\s+not\s+found\b)",
    re.I,
)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36"}


def fetch(url: str, attempts: int = 2, limit: int = 30000):
    """Bounded GET -> (status, body). Retry bei Timeout/Netzfehler (Volt-Seiten
    antworten sporadisch nicht). 0 erst nach allen Versuchen."""
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, r.read(limit).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:
            if i == attempts - 1:
                return 0, f"ERR {e}"
    return 0, "ERR"


def is_error_page(body: str) -> bool:
    """Fehlerseite? (404-Titel/Not-found-Text im Kopfbereich)"""
    return bool(JUNK_RE.search(body[:4000]))


def junk_docs() -> list[Path]:
    """Cache-Dokumente, die nur eine Fehlerseite enthalten (Kopf oder erste Zeilen)."""
    out = []
    for f in sorted(CACHE.glob("*.txt")):
        text = f.read_text(encoding="utf-8", errors="replace")
        first_lines = "\n".join(l.strip() for l in text.split("\n") if l.strip())[:200]
        if JUNK_RE.search(text[:4000]) or ("404" in first_lines and "not found" in first_lines.lower()):
            out.append(f)
    return out


def check_urls(urls: list[str]) -> list[tuple[str, int, str]]:
    with cf.ThreadPoolExecutor(16) as ex:
        return list(ex.map(lambda u: (u, *fetch(u)), urls))


def main():
    fix = "--fix" in sys.argv
    problems = []

    # 1) policy_pages aus chapters.json
    cfg = json.loads((ROOT / "scripts" / "chapters.json").read_text(encoding="utf-8"))
    jobs = []
    for name, info in cfg["chapters"].items():
        site = info.get("website", "").rstrip("/")
        for p in info.get("policy_pages", []):
            jobs.append((info["country"], name, site + p))
    print(f"== policy_pages: {len(jobs)} URLs in {len(cfg['chapters'])} Kapiteln")
    for (cc, name, url), (_, code, body) in zip(jobs, check_urls([j[2] for j in jobs])):
        bad = code != 200 or is_error_page(body)
        if bad:
            problems.append(f"{cc} {name}: {url} -> HTTP {code}{' (Fehlerseite)' if is_error_page(body) else ''}")
        print(f"  {'!!' if bad else 'OK'} {cc:3} {code:>4} {url}")

    # 2) known_pdfs.json
    kp_path = ROOT / "known_pdfs.json"
    if kp_path.exists():
        kp = json.loads(kp_path.read_text(encoding="utf-8"))
        dead = []
        for section in ("html_pages", "pdfs"):
            urls = list(kp.get(section, {}))
            if not urls:
                continue
            print(f"== known_pdfs.{section}: {len(urls)} URLs")
            for url, (_, code, body) in zip(urls, check_urls(urls)):
                if code != 200 or is_error_page(body):
                    dead.append((section, url, code))
                    print(f"  !! {code:>4} {url}")
        total_known = sum(len(kp.get(s, {})) for s in ("html_pages", "pdfs"))
        print(f"  -> tot: {len(dead)}/{total_known}")
        if dead and fix:
            for section, url, _ in dead:
                kp.get(section, {}).pop(url, None)
            kp_path.write_text(json.dumps(kp, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  -> {len(dead)} toten Eintraegen aus known_pdfs.json entfernt (werden neu gescrapt)")

        # 2b) Verwaiste Eintraege: URL registriert, aber kein passendes Cache-Dokument
        norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        stems = {norm(f.stem) for f in CACHE.glob("*.txt")}
        orphan = []
        for section in ("html_pages", "pdfs"):
            for url, meta in list(kp.get(section, {}).items()):
                base = url.split("?")[0].rstrip("/").split("/")[-1].replace(".pdf", "")
                if norm(meta.get("name") or "") not in stems and norm(base) not in stems:
                    orphan.append((section, url, meta.get("name")))
        print(f"== verwaiste known_pdfs-Eintraege (Cache-Datei fehlt): {len(orphan)}")
        for section, url, name in orphan:
            print(f"  !! {name}  <- {url}")
            problems.append(f"known_pdfs-Eintrag ohne Cache-Datei: {name}")
        if orphan and fix:
            for section, url, _ in orphan:
                kp.get(section, {}).pop(url, None)
            kp_path.write_text(json.dumps(kp, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  -> {len(orphan)} verwaiste Eintraege entfernt (werden neu gescrapt)")

    # 3) Fehlseiten im Cache
    junk = junk_docs()
    print(f"== Fehlseiten-Dokumente im Cache: {len(junk)}")
    for f in junk:
        print(f"  !! {f.name}")
        problems.append(f"Cache-Dokument ohne Inhalt (nur Fehlerseite): {f.name}")
    if junk and fix:
        dest = ROOT.parent.parent / "archive" / "volt-404-junk-2026-09"
        dest.mkdir(parents=True, exist_ok=True)
        for f in junk:
            for p in (f, f.with_name(f.stem + "_meta.json")):
                if p.exists():
                    shutil.move(str(p), str(dest / p.name))
        print(f"  -> {len(junk)} Dokumente nach {dest} verschoben (nichts geloescht)")

    if CHUNKS.exists():
        chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
        bad = sum(1 for c in chunks if is_error_page(str(c.get("text", ""))))
        print(f"== Index-Chunks (cache/chunks.json): {len(chunks)}, davon Fehlerseiten-Chunks: {bad}")
        if bad:
            problems.append(f"{bad} Index-Chunks enthalten nur Fehlerseiten -> build_index.py neu laufen lassen")

        # Policy-Chunks je Kapitel (0 = Land hat keine indizierte Policy)
        policy_sources = [str(c.get("source", "")) for c in chunks if c.get("type") == "policy"]
        print("== Policy-Chunks je Kapitel:")
        empty = []
        for name, info in cfg["chapters"].items():
            if not info.get("policy_pages"):
                continue  # bewusst ohne Policy-Seite (FI/LV/LT)
            cc = info["country"]
            pat = re.compile(rf"(?:{re.escape(name.lower())}|\b{cc.lower()}\b)", re.I)
            hits = [s for s in policy_sources if pat.search(s)]
            nchunks = sum(1 for s in policy_sources if pat.search(s))
            print(f"  {'!!' if nchunks == 0 else 'OK'} {cc:3} {name:28} {nchunks:5} Chunks / {len(set(hits))} Quellen")
            if nchunks == 0:
                empty.append(f"{cc} {name}")
        problems += [f"Kapitel ohne indizierte Policy: {e}" for e in empty]

    print(f"\n== Ergebnis: {len(problems)} Problem(e)")
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
