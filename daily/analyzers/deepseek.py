from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import jsonschema
import requests

from daily.analyzers.base import AnalyzerProvider
from daily.analyzers.prompt import SYSTEM_PROMPT
from daily.models import EconomicEvent


class DeepSeekAnalyzer(AnalyzerProvider):
    endpoint = "https://api.deepseek.com/chat/completions"

    def __init__(self, cache_dir: Path, api_key: str | None = None, model: str | None = None,
                 schema_path: Path | None = None, retries: int = 2):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_path or Path(__file__).parents[1] / "schemas" / "analysis-v1.json"
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.retries = retries
        self.last_usage: dict = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, event: EconomicEvent, documents: list[dict]) -> dict:
        if not self.enabled:
            return {}
        source = json.dumps({"event": event.to_dict(), "documents": documents}, ensure_ascii=False, sort_keys=True)
        cache_key = hashlib.sha256((self.model + source).encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))["analysis"]
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": source[:60000]}],
            "temperature": 0.1,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                response = requests.post(self.endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload, timeout=90)
                response.raise_for_status()
                body = response.json()
                analysis = json.loads(body["choices"][0]["message"]["content"])
                jsonschema.validate(analysis, self.schema)
                self.last_usage = {**body.get("usage", {}), "duration_seconds": round(time.monotonic() - started, 3), "model": self.model}
                cache_path.write_text(json.dumps({"analysis": analysis, "usage": self.last_usage}, ensure_ascii=False, indent=2), encoding="utf-8")
                return analysis
            except (requests.RequestException, KeyError, ValueError, jsonschema.ValidationError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1 + attempt)
        raise RuntimeError(f"DeepSeek 分析失败: {last_error}")
