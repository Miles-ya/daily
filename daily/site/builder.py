from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def normalize_base_url(value: str) -> str:
    return "/" if value == "/" else f"/{value.strip('/')}/"


def _date_parts(value: str) -> dict[str, str]:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return {
            "iso": value,
            "year": str(parsed.year),
            "month": parsed.strftime("%B").upper(),
            "month_short": parsed.strftime("%b").upper(),
            "month_number": parsed.strftime("%m"),
            "day": parsed.strftime("%d"),
            "weekday": parsed.strftime("%a").upper(),
            "display": parsed.strftime("%Y.%m.%d"),
        }
    except (TypeError, ValueError):
        return {"iso": value or "", "year": "—", "month": "UNDATED", "month_short": "—", "month_number": "00", "day": "—", "weekday": "—", "display": value or "日期未知"}


def _timeline(events: list[dict], digests: list[dict]) -> list[dict]:
    events_by_date: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        events_by_date[event.get("date") or ""].append(event)
    digest_by_date = {digest.get("date", ""): digest for digest in digests}
    dates = sorted(set(events_by_date) | set(digest_by_date), reverse=True)
    sections = []
    for value in dates:
        dated_events = sorted(events_by_date.get(value, []), key=lambda event: (bool(event.get("featured")), event.get("score", 0)), reverse=True)
        sections.append({
            **_date_parts(value),
            "events": dated_events,
            "digest": digest_by_date.get(value),
            "selected_count": sum(bool(event.get("featured")) for event in dated_events),
        })
    return sections


def _archive(timeline: list[dict]) -> list[dict]:
    years: list[dict] = []
    for section in timeline:
        year = next((item for item in years if item["year"] == section["year"]), None)
        if year is None:
            year = {"year": section["year"], "months": []}
            years.append(year)
        month = next((item for item in year["months"] if item["name"] == section["month"]), None)
        if month is None:
            month = {"name": section["month"], "number": section["month_number"], "days": []}
            year["months"].append(month)
        month["days"].append(section)
    return years


def build_site(root: Path, output: Path, base_url: str, documents: list[dict], events: list[dict], digests: list[dict], metrics: list[dict]) -> None:
    base_url = normalize_base_url(base_url)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    env = Environment(loader=FileSystemLoader(root / "daily/site/templates"), autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.globals["base_url"] = base_url
    env.globals["asset"] = lambda path: base_url + path.lstrip("/")
    docs_by_id = {d["id"]: d for d in documents}
    timeline = _timeline(events, digests)
    context = {
        "events": events,
        "documents": docs_by_id,
        "digests": digests,
        "metrics": metrics,
        "channel": "economy",
        "timeline": timeline,
        "archive": _archive(timeline),
        "updated": timeline[0]["display"] if timeline else "—",
    }

    pages = {
        "index.html": ("feed.html", {**context, "title": "Economy"}),
        "archive/index.html": ("archive.html", {**context, "title": "Archive"}),
        "all/index.html": ("archive.html", {**context, "title": "Archive"}),
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
