# Volt Policies

Shared cache + MCP server for the **Volt Policy Reference Checker**.

## What's in here

- `cache/*.txt` — Extracted text from 32+ Volt policy PDFs
- `cache/news_*.json` — RSS news feeds (auto-updated every 6 hours)
- `mcp_server.py` — MCP server for use from any MCP client
- `.github/workflows/` — Auto-updates PDFs + news every 6 hours

## Quick Start

### As Hermes Skill (already configured)
```bash
python3 volt_policy_checker.py search "climate"
```

### As MCP Server

**1. Clone the repo:**
```bash
git clone git@github.com:harrytyp/voltpolicies.git ~/.hermes/volt-policy-cache
```

**2. Install dependencies:**
```bash
pip install mcp pymupdf
```

**3. Configure your MCP client:**

Add to your MCP config (e.g., `~/.hermes/config.yaml` or VS Code settings):

```json
{
  "mcpServers": {
    "volt-policies": {
      "command": "python3",
      "args": ["~/.hermes/volt-policy-cache/mcp_server.py"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `volt_search(query)` | Search policy documents |
| `volt_search_news(query)` | Search news/press mentions |
| `volt_check(statement)` | Verify a claim against policy |
| `volt_verify_citation(citation)` | Check if a citation exists |
| `volt_fetch_news()` | Refresh RSS feeds |
| `volt_cache_status()` | Show cache info |

### Available Resources

| Resource | Description |
|----------|-------------|
| `volt://policies/list` | List all policy documents |
| `volt://news/latest` | Get latest news articles |

## Auto-Update

GitHub Actions runs every 6 hours:
1. Scrapes Volt websites for new PDFs
2. Fetches RSS news feeds
3. Commits changes automatically

## Manual Update

```bash
# Pull latest
git -C ~/.hermes/volt-policy-cache pull

# Or use the skill
python3 volt_policy_checker.py sync
```
