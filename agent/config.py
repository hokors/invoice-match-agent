"""Reads settings from .env in the repo root (standard library only)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict:
    values = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    values.update({k: v for k, v in os.environ.items() if k in values or k.startswith(("ODOO_", "GEMINI_"))})
    return values
