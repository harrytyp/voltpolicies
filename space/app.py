#!/usr/bin/env python3
"""
Volt Policy Chatbot — FAISS Semantic Search.
Multilingual, production-ready, auto-updating via GitHub.
Non-blocking startup: Gradio sofort verfügbar, Index lädt im Hintergrund.
"""
import json, os, subprocess, re, sys, threading, datetime, logging, shutil
from pathlib import Path
import gradio as gr
import httpx

# ── Config ──────────────────────────────────────────────────────────────────
GIT_REPO = "https://github.com/harrytyp/voltpolicies.git"
BASE = Path("/data/cache/repo")
CACHE_PATH = BASE / "cache"
LOG = logging.getLogger("volt")

# ── Thread-safe State ───────────────────────────────────────────────────────
FAISS_READY = [False]
FAISS_INFO = ["⏳ FAISS Index wird geladen..."]
SEARCH_MODULE = [None]

# ── Background Initialization ───────────────────────────────────────────────
def _init_async():
    """Run setup + FAISS import in background thread. Gradio starts immediately."""
    # Step 1: Fresh clone (delete entire old repo, then clone)
    for attempt in range(1, 4):
        try:
            if BASE.exists():
                shutil.rmtree(str(BASE), ignore_errors=True)
            BASE.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--depth", "1", GIT_REPO, str(BASE)],
                           capture_output=True, timeout=120)
            break
        except Exception as e:
            LOG.warning("Git attempt %d/3 failed: %s", attempt, e)

    # Step 2: Check if search_semantic exists after clone
    search_module_path = BASE / "scripts" / "search_semantic.py"
    if not search_module_path.exists():
        FAISS_INFO[0] = "⏳ Repository wird geladen — bitte 1-2 Minuten warten..."
        threading.Timer(30.0, _retry_init).start()
        return

    os.environ["VOLT_CACHE_DIR"] = str(CACHE_PATH)
    sys.path.insert(0, str(BASE))
    sys.path.insert(0, str(BASE / "scripts"))
    sys.path.insert(0, str(BASE / ".github" / "scripts"))

    try:
        import search_semantic as ss
        SEARCH_MODULE[0] = ss
        if ss.index_available():
            FAISS_READY[0] = True
            idx, _ = ss._load_index()
            n = idx.ntotal if idx else 0
            FAISS_INFO[0] = f"✅ FAISS Vektorsuche aktiv ({n} Vektoren)"
            LOG.info("FAISS ready: %d vectors", n)
        else:
            FAISS_INFO[0] = "⚠️ FAISS Index nicht gefunden — CI Build ausstehend?"
    except Exception as e:
        FAISS_INFO[0] = f"⚠️ FAISS nicht verfügbar: {e}"
        LOG.error("FAISS init failed: %s", e)


def _retry_init():
    """Retry initialization after a delay (git clone might still be in progress)."""
    search_module_path = BASE / "scripts" / "search_semantic.py"
    if not search_module_path.exists():
        FAISS_INFO[0] = "⏳ Repository wird noch geladen..."
        threading.Timer(30.0, _retry_init).start()
        return
    _init_async()

threading.Thread(target=_init_async, daemon=True).start()

# ── Daily Git Pull ──────────────────────────────────────────────────────────
def _puller():
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
        threading.Event().wait((target - now).total_seconds())
        try:
            subprocess.run(["git", "-C", str(BASE), "pull", "--ff-only"],
                           capture_output=True, timeout=30)
        except Exception:
            pass

_th = threading.Thread(target=_puller, daemon=True)
_th.start()

# ── API Keys ────────────────────────────────────────────────────────────────
MISTRAL_KEY    = os.environ.get("MISTRAL_API_KEY", os.environ.get("mistral", ""))
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", os.environ.get("openrouter", ""))
NVIDIA_KEY     = os.environ.get("NVIDIA_API_KEY", os.environ.get("nvidia_nim", ""))

# ── Tool Implementations ────────────────────────────────────────────────────
def _semantic_search(query, max_results=10):
    if not FAISS_READY[0] or SEARCH_MODULE[0] is None:
        return None
    return SEARCH_MODULE[0].semantic_search(query, max_results=max_results)


def search_policies(query: str, max_results: int = 5) -> str:
    results = _semantic_search(query, max_results)
    if results is None:
        return json.dumps({"results": [], "note": FAISS_INFO[0]})
    if not results:
        return json.dumps({"results": [], "note": "Keine Ergebnisse gefunden."})
    lines = [f"Search results ({len(results)} documents):"]
    for r in results:
        title = r.get("title", "")
        url = r.get("url", "")
        score = r.get("score", 0)
        preview = (r.get("text_preview") or "")[:300]
        lines.append(f"\n- {title} (Score: {score:.2f})")
        if url:
            lines.append(f"  URL: {url}")
        if preview:
            lines.append(f"  Excerpt: ...{preview}...")
    return "\n".join(lines)


def search_news(query: str, max_results: int = 8) -> list:
    results = _semantic_search(query, max_results * 2)
    if results is None:
        return [{"error": FAISS_INFO[0]}]
    news = [r for r in results if r.get("type") == "news"]
    return news[:max_results]


def check_statement(statement: str) -> dict:
    results = _semantic_search(statement, 5)
    if results is None:
        return {"statement": statement, "verdict": "NO_MATCH", "confidence": "LOW",
                "sources": [], "note": FAISS_INFO[0]}
    score = results[0]["score"] if results else 0
    if score >= 0.7:
        verdict, confidence = "MATCH", "HIGH"
    elif score >= 0.4:
        verdict, confidence = "PARTIAL", "MEDIUM"
    else:
        verdict, confidence = "NO_MATCH", "LOW"
    return {"statement": statement, "verdict": verdict, "confidence": confidence,
            "sources": results[:3]}


def verify_citation(citation: str) -> dict:
    results = _semantic_search(citation, 3)
    if results is None:
        return {"citation": citation, "found": False, "sources": [], "note": FAISS_INFO[0]}
    found = any(r.get("score", 0) > 0.8 for r in results)
    return {"citation": citation, "found": found, "sources": results[:3]}

# ── LLM API ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Volt Europa / Volt Deutschland policy assistant. You have 4 tools.

CRITICAL — ONLY USE URLs FROM TOOL RESULTS:
- NEVER invent URLs or page numbers. They come from your tool results.
- Format: **[Document, p. X](URL)** — copy the URL as-is from results.
- The tool results ARE your only knowledge source.

Tools:
1. search_policies(query) — search policy documents
2. search_news(query) — search news articles
3. check_statement(statement) — check a claim
4. verify_citation(citation) — verify a citation

Answer in EN or DE — match user."""

TOOLS = [
    {"type": "function", "function": {"name": "search_policies", "description": "Search Volt policy documents for a topic",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "e.g. 'EU reform', 'Drogenpolitik'"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_news", "description": "Search Volt news articles",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "e.g. 'ICC', 'election'"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "check_statement", "description": "Check a claim against Volt policy docs",
        "parameters": {"type": "object", "properties": {"statement": {"type": "string", "description": "Claim to verify"}}, "required": ["statement"]}}},
    {"type": "function", "function": {"name": "verify_citation", "description": "Check if a citation exists in documents",
        "parameters": {"type": "object", "properties": {"citation": {"type": "string", "description": "Text to find"}}, "required": ["citation"]}}},
]

def api_chat(backend, model, msgs, tools=None):
    endpoints = {
        "mistral":    ("https://api.mistral.ai/v1/chat/completions", MISTRAL_KEY),
        "openrouter": ("https://openrouter.ai/api/v1/chat/completions", OPENROUTER_KEY),
        "nvidia":     ("https://integrate.api.nvidia.com/v1/chat/completions", NVIDIA_KEY),
    }
    if backend not in endpoints:
        return None, "⚠️ Unknown backend"
    url, key = endpoints[backend]
    if not key:
        return None, f"⚠️ No API key configured for {backend}. Add it in Space Settings."
    body = {"model": model, "messages": msgs, "temperature": 0.3, "max_tokens": 2048}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    try:
        r = httpx.post(url, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://huggingface.co/spaces/harrytyp/voltpolicies",
        }, json=body, timeout=60)
        r.raise_for_status()
        return r.json(), None
    except httpx.HTTPStatusError as e:
        return None, f"⚠️ API Error ({e.response.status_code}): {e.response.text[:200]}"
    except httpx.TimeoutException:
        return None, "⚠️ API timeout (60s). The model is overloaded — try again."
    except Exception as e:
        return None, f"⚠️ Error: {e}"

def chat(msg, history, model_key):
    if not model_key or ":" not in model_key:
        return "⚠️ Bitte ein Modell auswählen."
    backend, model_id = model_key.split(":", 1)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": msg})
    tool_log = []

    for turn in range(5):
        resp, err = api_chat(backend, model_id, msgs, tools=TOOLS)
        if err:
            return err
        choice = resp["choices"][0]["message"]
        if not choice.get("tool_calls"):
            final = choice.get("content", "") or "(no answer)"
            if isinstance(final, list):
                final = " ".join(str(p.get("text", "")) for p in final if isinstance(p, dict))
            if tool_log:
                final = "🤔 *Tool calls:*\n" + "\n".join(tool_log) + "\n\n---\n\n" + final
            return final
        for tc in choice["tool_calls"]:
            fn = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            icons = {"search_policies": "🔍", "search_news": "📰",
                     "check_statement": "✅", "verify_citation": "📖"}
            arg_val = list(args.values())[0] if args else ""
            tool_log.append(f"  {icons.get(fn, '🔧')} {fn}(\"{arg_val}\")")
            try:
                if fn == "search_policies":
                    _, result = search_policies(args.get("query", msg))
                    result = {"formatted": result}
                elif fn == "search_news":
                    result = search_news(args.get("query", ""))
                elif fn == "check_statement":
                    result = check_statement(args.get("statement", ""))
                elif fn == "verify_citation":
                    result = verify_citation(args.get("citation", ""))
                else:
                    result = {"error": "Unknown tool"}
            except Exception as e:
                result = {"error": str(e)}
            count = len(result) if isinstance(result, list) else 1
            tool_log.append(f"  ⏱ {count} result(s)")
            content = json.dumps(result, ensure_ascii=False) if isinstance(result, (list, dict)) else str(result)
            msgs.append({"role": "assistant", "content": None, "tool_calls": [tc]})
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": content})

    resp, err = api_chat(backend, model_id, msgs)
    if err:
        return err
    final = resp["choices"][0]["message"].get("content", "") or "(no answer)"
    if isinstance(final, list):
        final = " ".join(str(p.get("text", "")) for p in final if isinstance(p, dict))
    if tool_log:
        final = "🤔 *Tool calls:*\n" + "\n".join(tool_log) + "\n\n---\n\n" + final
    return final

# ── Model Selection ─────────────────────────────────────────────────────────
BACKENDS = [
    ("🇫🇷 Mistral AI", "mistral", MISTRAL_KEY, [
        ("mistral-small-latest", "Mistral Small", "128K"),
        ("mistral-large-latest", "Mistral Large", "128K"),
    ]),
    ("🌐 OpenRouter (Free)", "openrouter", OPENROUTER_KEY, [
        ("openrouter/free", "Auto (best free)", "128K"),
        ("meta-llama/llama-3.1-8b-instruct:free", "Llama 3.1 8B", "128K"),
        ("mistralai/mistral-7b-instruct-v0.3:free", "Mistral 7B", "32K"),
        ("google/gemini-2.0-flash-exp:free", "Gemini Flash", "32K"),
    ]),
    ("🇺🇸 NVIDIA NIM", "nvidia", NVIDIA_KEY, [
        ("meta/llama-3.1-8b-instruct", "Llama 3.1 8B", "128K"),
        ("mistralai/mistral-large", "Mistral Large", "128K"),
        ("deepseek-ai/deepseek-v4-flash", "DeepSeek V4 Flash", "128K"),
        ("google/gemma-4-31b-it", "Gemma 4 31B", "32K"),
        ("ibm/granite-3.0-8b-instruct", "Granite 3.0 🇪🇺", "128K"),
    ]),
    ("💻 Local CPU", "cpu", "always_ok", [
        ("cpu_llama32_1b", "Llama 3.2 1B", "128K"),
    ]),
]

def build_choices():
    cs = []
    for lab, key, key_val, models in BACKENDS:
        cs.append((f"─── {lab} ───", f"_sep_{key}"))
        for mid, mlabel, ctx in models:
            ok = bool(key_val) if key_val != "always_ok" else True
            cs.append((f"{'🟢' if ok else '🔴'} {mlabel} ({ctx})", f"{key}:{mid}"))
    return cs

choices = build_choices()
default_val = next((v for _, v in choices if v and not v.startswith("_sep_")), None)

# ── Gradio UI ───────────────────────────────────────────────────────────────
CSS = """footer { display: none !important; }"""

with gr.Blocks(title="Volt Policy Chatbot", fill_height=True, css=CSS,
               theme=gr.themes.Soft(primary_hue="purple", secondary_hue="indigo")) as demo:

    status_display = gr.Markdown(f"## 💜 Volt Policy Chatbot\n4 tools · multilingual FAISS search · daily CI updates  \n{FAISS_INFO[0]}")

    with gr.Row():
        dd = gr.Dropdown(choices=choices, label="Model", value=default_val, interactive=True, scale=4,
                         info="🟢 = API-Key aktiv · 🔴 = kein Key")
        refresh_btn = gr.Button("🔄", variant="secondary", scale=0, min_width=60)
        refresh_btn.click(fn=lambda: gr.Dropdown(choices=build_choices()), outputs=[dd])

    gr.ChatInterface(fn=chat, type="messages", additional_inputs=[dd], title="")

    gr.Markdown(f"**Source:** [github.com/harrytyp/voltpolicies]({GIT_REPO}) · daily CI · "
                f"FAISS multilingual search · policy + news vectors")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
