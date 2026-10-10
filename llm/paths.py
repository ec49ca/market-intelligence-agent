"""Paths for the Karpathy-style wiki vault (repo root)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
WIKI_DIR = ROOT / "wiki"
OUTPUTS_DIR = ROOT / "outputs"
SCHEMA_PATH = WIKI_DIR / "AGENTS.md"
INDEX_PATH = WIKI_DIR / "index.md"
LOG_PATH = WIKI_DIR / "log.md"
