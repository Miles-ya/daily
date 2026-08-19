from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, root: Path):
        self.root = root

    def path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def read_json(self, *parts: str, default: Any = None) -> Any:
        path = self.root.joinpath(*parts)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, value: Any, *parts: str) -> Path:
        path = self.path(*parts)
        rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if not path.exists() or path.read_text(encoding="utf-8") != rendered:
            path.write_text(rendered, encoding="utf-8")
        return path
