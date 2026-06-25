#!/usr/bin/env python3
"""Volt Policy Chatbot — Gradio, Tool-Calling, _meta.json support."""
import json, os, subprocess, re, html
from pathlib import Path
import gradio as gr
import httpx
import threading as _th
import datetime as _dt

GIT_REPO = "https://github.com/harrytyp/voltpolicies.git"
BASE = Path("/data/cache/repo")
CACHE_PATH = BASE / "cache"
MISTRAL_KEY  = os.environ.get("MISTRAL_API_KEY", os.environ.get("mistral",""))
NVIDIA_KEY   = os.environ.get("NVIDIA_API_KEY", os.environ.get("nvidia_nim",""))
OPENROUTER_KEY=os.environ.get("OPENROUTER_API_KEY", os.environ.get("openrouter",""))

def setup():
    BASE.mkdir(parents=True, exist_ok=True)
    cache = BASE / "cache"
    if cache.exists() and list(cache.glob("*.txt")):
        subprocess.run(["git","-C",str(BASE),"pull","--ff-only"], capture_output=True, timeout=30)
    else:
        subprocess.run(["git","clone","--depth","1",GIT_REPO,str(BASE)], capture_output=True, timeout=120)
    return cache

CACHE_PATH = setup()

# Daily git pull at 07:00 UTC
def _puller():
    while True:
        now = _dt.datetime.now(_dt.timezone.utc)
        target = now.replace(hour=7,minute=0,second=0,microsecond=0)
        if now >= target: target += _dt.timedelta(days=1)
        _th.Event().wait((target-now).total_seconds())
        try: subprocess.run(["git","-C",str(BASE),"pull","--ff-only"], capture_output=True, timeout=30)
        except: pass
_th.Thread(target=_puller, daemon=True).start()

DOC_URLS = {
    "amsterdam declaration":"https://volteuropa.org/storage/pdf/policies/amsterdam_declaration.pdf",
    "amsterdam declaration (supporting)":"https://volteuropa.org/storage/pdf/policies/supporting_document_amsterdam_declaration.pdf",
    "campaign narrative 2024":"https://volteuropa.org/storage/pdf/eu-elections-2024/campaign-narrative-2024-eu-elections.pdf",
    "mop 9.0 - smart state":"https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-1-smart-state.pdf",
    "mop 9.0 - economic renaissance":"https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-2-economic-renaissance.pdf",
    "mop 9.0 - social equality":"https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-3-social-equality.pdf",
    "mop 9.0 - global balance":"https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-4-global-balance.pdf",
    "mop 9.0 - citizen empowerment":"https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-5-citizen-empowerment.pdf",
    "mop 9.0 - eu reform":"https://volteuropa.org/storage/pdf/policies/mop-9.0-challenge-5-1-eu-reform.pdf",
    "economic vision":"https://volteuropa.org/storage/pdf/policies/the-economic-vision-of-volt-europa-final.pdf",
    "electoral reform":"https://volteuropa.org/storage/pdf/policies/electoral-reform-policy.pdf",
    "energy transition & climate change":"https://volteuropa.org/storage/pdf/policies/energy-transition-&-climate-change.pdf",
    "space policy":"https://volteuropa.org/storage/pdf/policies/volt-space-policy.pdf",
    "european constitution":"https://volteuropa.org/storage/pdf/policies/provisions-for-a-european-constitution.pdf",
    "mop 9.0 summary":"https://volteuropa.org/storage/pdf/policies/mop-9.0-executive-summary-final.pdf",
    "grundsatzprogramm 2023":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/grundsatzprogramm_volt_deutschland_2023_01_28.pdf",
    "grundsatzprogramm":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/grundsatzprogramm_volt_deutschland_2023_01_28.pdf",
    "bundestagswahl 2025":"https://voltdeutschland.org/storage/assets-btw25/volt-programm-bundestagswahl-2025.pdf",
    "bundestagswahl 2025 leichte sprache":"https://voltdeutschland.org/storage/assets-de/pdf/btw-wahl-2025/gepruftes-wahl-programm-leichte-sprache-volt-bundestags-wahl-2025.pdf",
    "europawahl 2024":"https://voltdeutschland.org/storage/assets-de/pdf/europawahl_2024/volt-wahlprogramm-europawahl-2024.pdf",
    "satzung":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/satzung_des_landesverbandes_volt_deutschland.pdf",
    "beitragsordnung":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/beitragsordnung_volt_deutschland.pdf",
    "allgemeine wahlordnung":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/allgemeine_wahlordnung_von_volt_deutschland.pdf",
    "finanzordnung":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/finanzordnung_des_landesverbandes_volt_deutschland.pdf",
    "schiedsordnung":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/schiedsordnung_des_landesverbandes_volt_deutschland.pdf",
    "geschäftsordnung bundesparteitage":"https://voltdeutschland.org/storage/assets-de/pdf/politische_programme_de/geschaeftsordnung_fuer_ordentliche_und_ausserordentliche_bundesparteitage_von_volt_deutschland.pdf",
    "position ehegattensplitting":"https://voltdeutschland.org/storage/assets-de/pdf/positionspapiere/positionspapier_ehegattensplitting.pdf",
    "position magnetschwebebahn":"https://voltdeutschland.org/storage/assets-de/pdf/positionspapiere/positionspapier_magnetschwebebahn.pdf",
    "wehrfähige eu":"https://voltdeutschland.org/storage/assets-de/pdf/positionspapiere/positionspapier_bundeswehr_wehrfahige_eu.pdf",
    "nukleare teilhabe":"https://voltdeutschland.org/storage/assets-de/pdf/positionspapiere/positionspapier_nukleare_teilhabe.pdf",
    "ehegattensplitting":"https://voltdeutschland.org/storage/assets-de/pdf/positionspapiere/positionspapier_ehegattensplitting.pdf",
    "magnetschwebebahn":"https://voltdeutschland.org/storage/assets-de/pdf/positionspapiere/positionspapier_magnetschwebebahn.pdf",
    "unvereinbarkeitsbeschluss antisemitismus":"https://voltdeutschland.org/storage/assets-sachsen/pdf/uvb-antisemitismus-und-zum-schutz-judischen-lebens-sachsen.pdf",
    "unvereinbarkeitsbeschluss linksextremismus":"https://voltdeutschland.org/storage/assets-schleswig-holstein/pdf/weitere/unvereinbarkeitsbeschluss-linksextremismus.pdf",
    "unvereinbarkeitsbeschluss afd":"https://voltdeutschland.org/storage/assets-schleswig-holstein/pdf/weitere/unvereinbarkeitsbeschluss-fur-jegliche-zusammenarbeit-mit-rassistischen,-rechtsextremen,-demokratie--und-verfassungsfeindlichen-gruppierungen-und-parteien,-insbesondere-der-afd.pdf",
    "wahlprogramm landtagswahl bayern 2023":"https://voltdeutschland.org/storage/assets-bayern/pdf/programme/wahlprogramm-landtagswahl-bayern-2023.pdf",
    "landtagswahlprogramm hessen 2023":"https://voltdeutschland.org/storage/assets-hessen/pdf/volt-hessen-2023-landtagswahlprogramm.pdf",
    "wahlprogramm rlp 2026":"https://voltdeutschland.org/storage/assets-rlp/pdf/20260213_wahlprogramm-rheinland-pfalz-zur_landtagswahl-2026.pdf",
    "eu moonshot programme 2024":"https://volteuropa.org/storage/pdf/policies/volt_-eur-electoral-moonshot-program_v5-final-(1).pdf",
    "eu campaign programme 2024":"https://volteuropa.org/storage/pdf/eu-elections-2024/europeancampaignprogramme_amended.pdf",
    "live animal transportation":"https://volteuropa.org/storage/pdf/policies/volt-position-on-live-animal-transportation.pdf",
}

def get_url_for_file(name: str) -> str:
    key = name.lower().strip()
    if key in DOC_URLS: return DOC_URLS[key]
    k2 = key.replace("_"," ")
    if k2 in DOC_URLS: return DOC_URLS[k2]
    k3 = re.sub(r'\s+\d{4}', '', key).strip()
    if k3 in DOC_URLS: return DOC_URLS[k3]
    return ""

USE_META = True  # will be False if no _meta.json found

def search_policies(query: str, max_results=5):
    """Return (results_list, formatted_text). Uses _meta.json when available."""
    global USE_META
    words = [w.lower() for w in query.split() if len(w) > 2]
    if not words or not CACHE_PATH: return [], json.dumps({"results":[],"note":"No docs"})
    res = []
    
    meta_files = {f.stem.replace("_meta",""): json.loads(f.read_text(encoding="utf-8"))
                  for f in CACHE_PATH.glob("*_meta.json")}
    
    if not meta_files:
        USE_META = False
    
    for f in CACHE_PATH.glob("*.txt"):
        stem = f.stem
        name = stem.replace("_"," ").strip()
        url_base = get_url_for_file(name)
        
        if stem in meta_files:
            USE_META = True
            for pg in meta_files[stem].get("pages", []):
                pn = pg["page"]; text = pg["text"]; low = text.lower()
                score = sum(low.count(w) for w in words)
                if score == 0: continue
                idxs = [low.find(w) for w in words if low.find(w)>=0]
                c = sum(idxs)//len(idxs) if idxs else 0
                s,e = max(0,c-200), min(len(text),c+500)
                url = f"{url_base}#page={pn}" if url_base else ""
                res.append({"doc":name,"page":str(pn),"url":url,"score":score,"snippet":text[s:e].strip()})
        else:
            text = f.read_text(encoding="utf-8",errors="replace")
            low = text.lower()
            score = sum(low.count(w) for w in words)
            if score == 0: continue
            idxs = [low.find(w) for w in words if low.find(w)>=0]
            c = sum(idxs)//len(idxs) if idxs else 0
            s,e = max(0,c-200), min(len(text),c+500)
            res.append({"doc":name,"page":"","url":url_base,"score":score,"snippet":text[s:e].strip()})
    
    res.sort(key=lambda x:-x["score"])
    top = res[:max_results]
    if not top: return [], json.dumps({"results":[],"note":"No results"})
    
    lines = [f"Search results ({len(top)} documents):"]
    for r in top:
        lines.append(f"\n- Document: {r['doc']}" + (f" (page {r['page']})" if r['page'] else ""))
        lines.append(f"  URL: {r['url']}" if r['url'] else "  (no external URL)")
        lines.append(f"  Excerpt: ...{r['snippet'][:300]}...")
    return top, "\n".join(lines)

def search_news(query: str, max_results=8):
    if not CACHE_PATH: return []
    q = query.lower().strip()
    show_all = q in ["","recent","latest","current","new","neueste","neuesten","neues",
                     "aktuell","aktuelle","aktuelles","alle","all","neuigkeiten","news","nachrichten"]
    res = []
    for nf in sorted(CACHE_PATH.glob("news_*.json")):
        try: arts = json.loads(nf.read_text(encoding="utf-8"))
        except: continue
        for a in arts if isinstance(arts,list) else arts.get("posts",[]):
            title = a.get('title','') or a.get('caption','') or ''
            desc = a.get('description','') or ''
            link = a.get('link','') or a.get('url','') or ''
            date = a.get('date','') or a.get('created_time','') or ''
            txt = (title+" "+desc).lower()
            if show_all or q in txt:
                res.append({"title":title[:200],"url":link,"date":date[:10],"source":nf.stem.replace("news_","").replace("_"," ")})
    res.sort(key=lambda x:x.get("date",""), reverse=True)
    return res[:max_results]

def check_statement(s: str) -> dict:
    docs, _ = search_policies(s, 3)
    s2 = docs[0]["score"] if docs else 0
    if s2 >= 100: v,h = "MATCH","HIGH"
    elif s2 >= 30: v,h = "PARTIAL","MEDIUM"
    else: v,h = "NO_MATCH","LOW"
    return {"statement":s,"verdict":v,"confidence":h,"sources":docs[:3]}

def verify_citation(c: str) -> dict:
    res, _ = search_policies(c, 3)
    f = any(r["score"]>0 for r in res)
    return {"citation":c,"found":f,"sources":res[:3] if f else []}

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
  {"type":"function","function":{"name":"search_policies","description":"Search Volt policy documents for a topic",
    "parameters":{"type":"object","properties":{"query":{"type":"string","description":"e.g. 'EU reform', 'Drogenpolitik'"}},"required":["query"]}}},
  {"type":"function","function":{"name":"search_news","description":"Search Volt news articles",
    "parameters":{"type":"object","properties":{"query":{"type":"string","description":"e.g. 'ICC', 'election'"}},"required":["query"]}}},
  {"type":"function","function":{"name":"check_statement","description":"Check a claim against Volt policy docs",
    "parameters":{"type":"object","properties":{"statement":{"type":"string","description":"Claim to verify"}},"required":["statement"]}}},
  {"type":"function","function":{"name":"verify_citation","description":"Check if a citation exists in documents",
    "parameters":{"type":"object","properties":{"citation":{"type":"string","description":"Text to find"}},"required":["citation"]}}},
]

def api_chat(backend, model, msgs, tools=None):
    if backend=="mistral":    url="https://api.mistral.ai/v1/chat/completions"; key=MISTRAL_KEY
    elif backend=="openrouter": url="https://openrouter.ai/api/v1/chat/completions"; key=OPENROUTER_KEY
    elif backend=="nvidia":   url="https://integrate.api.nvidia.com/v1/chat/completions"; key=NVIDIA_KEY
    else: return None,"⚠️ Unknown backend"
    if not key: return None,f"⚠️ No key for {backend}"
    body={"model":model,"messages":msgs,"temperature":0.3,"max_tokens":2048}
    if tools: body["tools"]=tools; body["tool_choice"]="auto"
    try:
        r = httpx.post(url, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json",
                         "HTTP-Referer":"https://huggingface.co/spaces/harrytyp/voltpolicies"},
                       json=body, timeout=60)
        r.raise_for_status(); return r.json(), None
    except httpx.HTTPStatusError as e:
        return None,f"⚠️ Error ({e.status_code}): {e.response.text[:200]}"
    except Exception as e:
        return None,f"⚠️ Error: {e}"

def chat(msg, history, model_key):
    if not model_key or ":" not in model_key:
        return "⚠️ Please select a model."
    backend, model_id = model_key.split(":",1)
    msgs = [{"role":"system","content":SYSTEM_PROMPT}]
    for h in history: msgs.append({"role":h["role"],"content":h["content"]})
    msgs.append({"role":"user","content":msg})
    tool_log = []
    for _ in range(5):
        resp, err = api_chat(backend, model_id, msgs, tools=TOOLS)
        if err: return err
        choice = resp["choices"][0]["message"]
        if not choice.get("tool_calls"):
            final = choice.get("content","") or "(no answer)"
            if isinstance(final, list):
                final = " ".join(str(p.get("text","")) for p in final if isinstance(p,dict))
            if tool_log:
                final = "🤔 *Tool calls:*\n" + "\n".join(tool_log) + "\n\n---\n\n" + final
            return final
        for tc in choice["tool_calls"]:
            fn = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            icons = {"search_policies":"🔍","search_news":"📰","check_statement":"✅","verify_citation":"📖"}
            arg_val = list(args.values())[0] if args else ""
            tool_log.append(f"  {icons.get(fn,'🔧')} {fn}(\"{arg_val}\")")
            if fn == "search_policies":
                _, result = search_policies(args.get("query",msg))
                result = {"formatted": result}
            elif fn == "search_news":     result = search_news(args.get("query",""))
            elif fn == "check_statement": result = check_statement(args.get("statement",""))
            elif fn == "verify_citation": result = verify_citation(args.get("citation",""))
            else: result = {"error":"Unknown tool"}
            count = len(result) if isinstance(result,list) else 1
            tool_log.append(f"  ⏱ {count} result(s)")
            content = json.dumps(result, ensure_ascii=False) if isinstance(result,(list,dict)) else str(result)
            msgs.append({"role":"assistant","content":None,"tool_calls":[tc]})
            msgs.append({"role":"tool","tool_call_id":tc["id"],"content":content})
    resp, err = api_chat(backend, model_id, msgs)
    if err: return err
    final = resp["choices"][0]["message"].get("content","") or "(no answer)"
    if isinstance(final, list):
        final = " ".join(str(p.get("text","")) for p in final if isinstance(p,dict))
    if tool_log:
        final = "🤔 *Tool calls:*\n" + "\n".join(tool_log) + "\n\n---\n\n" + final
    return final

BACKENDS = [
  ("🇫🇷 Mistral AI","mistral",MISTRAL_KEY,[("mistral-small-latest","Mistral Small","128K"),("mistral-large-latest","Mistral Large","128K")]),
  ("🌐 OpenRouter (Free)","openrouter",OPENROUTER_KEY,[("openrouter/free","Auto (best free)","128K"),("meta-llama/llama-3.1-8b-instruct:free","Llama 3.1 8B","128K"),("mistralai/mistral-7b-instruct-v0.3:free","Mistral 7B","32K"),("google/gemini-2.0-flash-exp:free","Gemini Flash","32K")]),
  ("🇺🇸 NVIDIA NIM","nvidia",NVIDIA_KEY,[("meta/llama-3.1-8b-instruct","Llama 3.1 8B","128K"),("mistralai/mistral-large","Mistral Large","128K"),("deepseek-ai/deepseek-v4-flash","DeepSeek V4 Flash","128K"),("google/gemma-4-31b-it","Gemma 4 31B","32K"),("google/diffusiongemma-26b-a4b-it","DiffusionGemma 26B","32K"),("nvidia/nemotron-3-ultra-550b-a55b","Nemotron 550B","128K"),("ibm/granite-3.0-8b-instruct","Granite 3.0 🇪🇺","128K"),("microsoft/phi-4-mini-instruct","Phi-4 Mini","128K")]),
  ("💻 Local CPU","cpu","always_ok",[("cpu_llama32_1b","Llama 3.2 1B","128K")]),
]

def build_choices():
    cs = []
    for lab,key,key_val,models in BACKENDS:
        cs.append((f"─── {lab} ───", f"_sep_{key}"))
        for mid,mlabel,ctx in models:
            ok = bool(key_val) if key_val!="always_ok" else True
            cs.append((f"{'🟢' if ok else '🔴'} {mlabel} ({ctx})", f"{key}:{mid}"))
    return cs

choices = build_choices()
default_val = next((v for _,v in choices if v and not v.startswith("_sep_")), None)

CSS = "footer { display: none !important; }"

with gr.Blocks(title="Volt Policy Chatbot", fill_height=True, css=CSS,
               theme=gr.themes.Soft(primary_hue="purple",secondary_hue="indigo")) as demo:
    gr.Markdown("## 💜 Volt Policy Chatbot\n4 tools · model decides when to search · daily CI updates")

    with gr.Row():
        dd = gr.Dropdown(choices=choices, label="Model", value=default_val, interactive=True, scale=4,
                         info="🟢 = key active · 🔴 = no key")
        gr.Button("🔄", variant="secondary", scale=0, min_width=60).click(
            fn=lambda: gr.Dropdown(choices=build_choices()), outputs=[dd])

    gr.ChatInterface(fn=chat, type="messages", additional_inputs=[dd], title="")

    gr.Markdown("**Source:** [github.com/harrytyp/voltpolicies](https://github.com/harrytyp/voltpolicies) · daily CI · 33 PDFs · page-accurate")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
