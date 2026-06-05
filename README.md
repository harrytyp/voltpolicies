# Volt Policies Cache

Shared cache for the **Volt Policy Reference Checker** Hermes skill.

## What's in here

- `cache/*.txt` — Extracted text from 32 Volt Europa + Volt Deutschland policy PDFs
- `cache/news_*.json` — RSS news feeds (auto-updated every 6 hours via GitHub Actions)

## Auto-Update

News feeds are automatically refreshed every 6 hours via GitHub Actions. The workflow:
1. Fetches latest RSS from Volt Deutschland, Volt Europa, and Mastodon
2. Updates the JSON files in `cache/`
3. Commits and pushes changes

## Setup on a new device

```bash
# Clone this repo
git clone https://github.com/harrytyp/voltpolicies.git ~/.hermes/volt-policy-cache

# Configure the skill to use it
python3 ~/.hermes/skills/research/volt-policy-reference-check/scripts/cache_manager.py \
  setup-github https://github.com/harrytyp/voltpolicies.git
```

## Manual update

```bash
# Pull latest
python3 ~/.hermes/skills/research/volt-policy-reference-check/scripts/volt_policy_checker.py sync
```
