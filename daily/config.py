from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_config(root: Path) -> dict:
    settings = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
    sources = yaml.safe_load((root / "config/sources.yaml").read_text(encoding="utf-8"))
    settings.update(sources)
    settings["site"]["base_url"] = os.getenv("SITE_BASE_URL", settings["site"]["base_url"])
    return settings
