from __future__ import annotations

import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def normalize_base_url(value: str) -> str:
    return "/" if value == "/" else f"/{value.strip('/')}/"


def build_site(root: Path, output: Path, base_url: str, documents: list[dict], events: list[dict], digests: list[dict], metrics: list[dict]) -> None:
    base_url = normalize_base_url(base_url)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    env = Environment(loader=FileSystemLoader(root / "daily/site/templates"), autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.globals["base_url"] = base_url
    env.globals["asset"] = lambda path: base_url + path.lstrip("/")
    docs_by_id = {d["id"]: d for d in documents}
    context = {"events": events, "documents": docs_by_id, "digests": digests, "metrics": metrics, "channel": "economy"}

    pages = {
        "index.html": ("feed.html", {**context, "title": "精选", "events": [e for e in events if e.get("featured")]}),
        "all/index.html": ("feed.html", {**context, "title": "全部经济动态"}),
        "hot/index.html": ("hot.html", {**context, "title": "当前热点"}),
        "daily/index.html": ("digest.html", {**context, "title": "经济日报", "digest": digests[-1] if digests else None}),
        "metrics/index.html": ("metrics.html", {**context, "title": "数据指标"}),
        "about/index.html": ("about.html", {**context, "title": "关于 Daily"}),
    }
    for relative, (template, values) in pages.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(**values), encoding="utf-8")
    for event in events:
        target = output / "events" / event["id"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template("event.html").render(**context, title=event["title"], event=event), encoding="utf-8")
    assets = output / "assets"
    assets.mkdir()
    for name in ("style.css", "app.js", "favicon.svg"):
        shutil.copy2(root / "daily/site/templates" / name, assets / name)
    search = [{"id": e["id"], "title": e["title"], "tags": e.get("tags", []), "score": e.get("score", 0),
               "summary": e.get("analysis", {}).get("one_sentence", ""), "url": f"events/{e['id']}/"} for e in events]
    (output / "search-index.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
