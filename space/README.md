---
title: Volt Policies MCP Server
emoji: 💜
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: true
license: mit
---

# Volt Policies MCP Server

MCP (Model Context Protocol) Server for Volt Europa and Volt Germany policy documents.

Provides policy search, news search, and consistency checking via MCP tools.

## Usage

### In Claude Desktop / Cursor / Windsurf / Any MCP Client

```json
{
  "mcpServers": {
    "volt-policies": {
      "type": "sse",
      "url": "https://YOUR-SPACE-NAME.hf.space/sse"
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `volt_search(query)` | Search policy PDFs with page numbers |
| `volt_search_news(query)` | Search news articles |
| `volt_check(statement)` | Verify claim vs. policy |
| `volt_verify_citation(citation)` | Check if citation exists |
| `volt_cache_status()` | Show cache info |

### Available Resources

| Resource | Description |
|----------|-------------|
| `volt://policies/list` | List all policy documents |

## Source

Repository: https://github.com/harrytyp/voltpolicies  
Cache auto-updated daily via GitHub Actions.
