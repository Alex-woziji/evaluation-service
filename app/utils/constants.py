"""Project-level constants (static paths, etc.)."""

from pathlib import Path

# app/utils/constants.py  →  app/utils/  →  app/  →  project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PROMPT_DIR = PROJECT_ROOT / "resource" / "prompt" / "prompt.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "evaluation.db"
