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
    default_endpoint = "https://api.deepseek.com/chat/completions"

    def __init__(self, cache_dir: Path, api_key: str | None = None, model: str | None = None,
                 schema_path: Path | None = None, retries: int = 2, system_prompt: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.endpoint = os.getenv("DEEPSEEK_BASE_URL", self.default_endpoint).rstrip("/")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_path or Path(__file__).parents[1] / "schemas" / "analysis-v1.json"
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.retries = retries
        self.last_usage: dict = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, event: EconomicEvent, documents: list[dict]) -> Path:
        identity = {
            "model": self.model,
            "schema": self.schema.get("$id", ""),
            "event_id": event.id,
            "documents": sorted((document.get("id", ""), document.get("content_hash", "")) for document in documents),
        }
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def prime_cache(self, event: EconomicEvent, documents: list[dict], analysis: dict) -> None:
        if not analysis:
            return
        jsonschema.validate(analysis, self.schema)
        path = self._cache_path(event, documents)
        if not path.exists():
            path.write_text(json.dumps({"analysis": analysis, "usage": {"migrated": True, "model": self.model}}, ensure_ascii=False, indent=2), encoding="utf-8")

    def analyze(self, event: EconomicEvent, documents: list[dict]) -> dict:
        self.last_usage = {}
        if not self.enabled:
            return {}
        event_input = event.to_dict()
        # AI output must never become part of its own next cache key/input.
        event_input["analysis"] = {}
        source = json.dumps({"event": event_input, "documents": documents}, ensure_ascii=False, sort_keys=True)
        cache_path = self._cache_path(event, documents)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))["analysis"]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps({"output_schema": self.schema, "input": json.loads(source)}, ensure_ascii=False)[:60000]},
            ],
            "temperature": 0.1,
            "max_tokens": 8000,
            "stream": True,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                response = requests.post(self.endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload, stream=True, timeout=(15, 90))
                response.raise_for_status()
                fragments: list[str] = []
                usage: dict = {}
                finish_reason: str | None = None
                chunk_buffer = b""
                for raw_line in response.iter_lines(decode_unicode=False):
                    if not raw_line:
                        continue
                    data = raw_line[5:].strip() if raw_line.startswith(b"data:") else raw_line.strip()
                    if data == b"[DONE]":
                        break
                    chunk_buffer += data
                    try:
                        chunk = json.loads(chunk_buffer.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        # Some compatible gateways split one SSE JSON event over
                        # physical lines without repeating the `data:` prefix.
                        continue
                    chunk_buffer = b""
                    usage = chunk.get("usage") or usage
                    # OpenAI-compatible gateways may emit usage-only chunks
                    # with an explicitly empty choices list near stream end.
                    choices = chunk.get("choices") or []
                    choice = choices[0] if choices else {}
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        fragments.append(delta["content"])
                if chunk_buffer:
                    raise ValueError("AI stream ended with an incomplete SSE event")
                raw_analysis = "".join(fragments).strip()
                if raw_analysis.startswith("```json") and raw_analysis.endswith("```"):
                    raw_analysis = raw_analysis[7:-3].strip()
                analysis = json.loads(raw_analysis)
                jsonschema.validate(analysis, self.schema)
                self.last_usage = {**usage, "duration_seconds": round(time.monotonic() - started, 3), "model": self.model,
                                   "finish_reason": finish_reason}
                cache_path.write_text(json.dumps({"analysis": analysis, "usage": self.last_usage}, ensure_ascii=False, indent=2), encoding="utf-8")
                return analysis
            except (requests.RequestException, KeyError, ValueError, jsonschema.ValidationError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1 + attempt)
        raise RuntimeError(f"DeepSeek 分析失败: {last_error}")
