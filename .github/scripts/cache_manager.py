#!/usr/bin/env python3
"""
Volt Policy Reference Checker — Cross-device cache manager.
Manages a shared GitHub repo cache for PDFs, extracted text, and news.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Default cache locations (checked in order)
DEFAULT_CACHE_PATHS = [
    Path.home() / ".hermes" / "skills" / "research" / "volt-policy-reference-check" / "cache",
]

# Config file location
CONFIG_PATH = Path.home() / ".hermes" / "skills" / "research" / "volt-policy-reference-check" / "config.json"


def load_config() -> dict:
    """Load configuration from config.json."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    """Save configuration to config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def get_cache_dir() -> Path:
    """Get the cache directory from config or default."""
    config = load_config()
    
    # Check for custom cache path
    if 'cache_dir' in config:
        custom = Path(config['cache_dir'])
        if custom.exists() or custom.parent.exists():
            return custom
    
    # Check for GitHub repo
    if 'github_repo' in config:
        repo_path = Path.home() / ".hermes" / "volt-policy-cache"
        if repo_path.exists():
            return repo_path / "cache"
    
    # Default
    return DEFAULT_CACHE_PATHS[0]


def setup_github_repo(repo_url: str):
    """Clone or pull a GitHub repo for shared cache."""
    repo_path = Path.home() / ".hermes" / "volt-policy-cache"
    
    if repo_path.exists():
        print(f"Pulling latest from {repo_url}...")
        result = subprocess.run(
            ["git", "-C", str(repo_path), "pull"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print("  ✓ Updated successfully")
        else:
            print(f"  Warning: git pull failed: {result.stderr}")
    else:
        print(f"Cloning {repo_url}...")
        result = subprocess.run(
            ["git", "clone", repo_url, str(repo_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print("  ✓ Cloned successfully")
        else:
            print(f"  Error: git clone failed: {result.stderr}")
            return False
    
    # Ensure cache subdirectory exists
    cache_dir = repo_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    
    # Save config
    config = load_config()
    config['github_repo'] = repo_url
    config['cache_dir'] = str(cache_dir)
    save_config(config)
    
    return True


def setup_custom_path(path: str):
    """Set a custom cache directory path."""
    custom = Path(path)
    custom.mkdir(parents=True, exist_ok=True)
    
    config = load_config()
    config['cache_dir'] = str(custom)
    save_config(config)
    
    print(f"Cache directory set to: {custom}")
    return True


def push_to_github(commit_message: str = "Update Volt policy cache"):
    """Push local cache changes to GitHub."""
    config = load_config()
    if 'github_repo' not in config:
        print("No GitHub repo configured. Use: python cache_manager.py setup-github <repo_url>")
        return False
    
    repo_path = Path.home() / ".hermes" / "volt-policy-cache"
    if not repo_path.exists():
        print("Repo not found locally. Run setup-github first.")
        return False
    
    # Stage changes
    subprocess.run(["git", "-C", str(repo_path), "add", "."], capture_output=True)
    
    # Check for changes
    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        capture_output=True, text=True
    )
    
    if not result.stdout.strip():
        print("No changes to commit")
        return True
    
    # Commit
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", commit_message],
        capture_output=True, text=True
    )
    
    # Push
    print("Pushing to GitHub...")
    result = subprocess.run(
        ["git", "-C", str(repo_path), "push"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode == 0:
        print("  ✓ Pushed successfully")
        return True
    else:
        print(f"  Warning: git push failed: {result.stderr}")
        return False


def show_status():
    """Show current cache configuration and status."""
    config = load_config()
    cache_dir = get_cache_dir()
    
    print("=== Volt Policy Cache Configuration ===")
    print(f"Config file: {CONFIG_PATH}")
    
    if 'github_repo' in config:
        print(f"GitHub repo: {config['github_repo']}")
    elif 'cache_dir' in config:
        print(f"Custom path: {config['cache_dir']}")
    else:
        print("Using default local cache")
    
    print(f"Cache directory: {cache_dir}")
    
    if cache_dir.exists():
        pdfs = list(cache_dir.glob("*.pdf"))
        txts = list(cache_dir.glob("*.txt"))
        news = list(cache_dir.glob("news_*.json"))
        total_size = sum(f.stat().st_size for f in cache_dir.iterdir()) / (1024 * 1024)
        
        print(f"\n=== Cache Contents ===")
        print(f"PDFs: {len(pdfs)}")
        print(f"Text files: {len(txts)}")
        print(f"News feeds: {len(news)}")
        print(f"Total size: {total_size:.1f} MB")
    else:
        print("\nCache directory does not exist yet")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python cache_manager.py setup-github <repo_url>  - Set up GitHub repo sync")
        print("  python cache_manager.py setup-path <path>        - Set custom cache path")
        print("  python cache_manager.py pull                     - Pull latest from GitHub")
        print("  python cache_manager.py push [message]           - Push changes to GitHub")
        print("  python cache_manager.py status                   - Show configuration")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "setup-github":
        if len(sys.argv) < 3:
            print("Usage: python cache_manager.py setup-github <repo_url>")
            sys.exit(1)
        setup_github_repo(sys.argv[2])
    
    elif command == "setup-path":
        if len(sys.argv) < 3:
            print("Usage: python cache_manager.py setup-path <path>")
            sys.exit(1)
        setup_custom_path(sys.argv[2])
    
    elif command == "pull":
        config = load_config()
        if 'github_repo' in config:
            setup_github_repo(config['github_repo'])
        else:
            print("No GitHub repo configured")
    
    elif command == "push":
        msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Update Volt policy cache"
        push_to_github(msg)
    
    elif command == "status":
        show_status()
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
