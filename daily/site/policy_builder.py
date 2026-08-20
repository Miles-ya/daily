from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from daily.site.builder import normalize_base_url


TOPIC_SLUGS = {"产业方向": "industry", "资金流向": "capital", "创业机会": "startup", "就业与城市": "career-city", "宏观环境": "macro"}


def build_policy_site(root: Path, output: Path, base_url: str, policies: list[dict], assessments: dict[str, dict], generated_on: str | None = None) -> None:
    base_url = normalize_base_url(base_url)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    template_root = root / "daily/site/templates"
    env = Environment(loader=FileSystemLoader(template_root), autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.globals["base_url"] = base_url
    versions = {name: hashlib.sha256((template_root / name).read_bytes()).hexdigest()[:10] for name in ("style.css", "app.js", "favicon.svg")}

    def asset(path: str) -> str:
        normalized = path.lstrip("/")
        name = Path(normalized).name
        suffix = f"?v={versions[name]}" if normalized.startswith("assets/") and name in versions else ""
        return base_url + normalized + suffix

    env.globals["asset"] = asset
    records = []
    for policy in policies:
        assessment = assessments.get(policy["id"])
        if (not assessment or not assessment.get("relevant", True)
                or policy.get("policy_status") == "interpretation"
                or policy.get("title", "").strip(" []") == "政策原文"):
            continue
        records.append({**policy, "assessment": assessment, "analysis": assessment.get("analysis", {})})
    records.sort(key=lambda item: (item.get("publish_date") or "", item.get("publish_time") or "", item.get("crawl_time") or ""), reverse=True)
    generated_on = generated_on or datetime.now().astimezone().replace(microsecond=0).isoformat()

    def write(relative: str, template: str, **values) -> None:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(records=records, topics=TOPIC_SLUGS, generated_on=generated_on, **values), encoding="utf-8")

    important = [item for item in records if item["assessment"].get("importance") == "important"]
    write("index.html", "policy_feed.html", title="政策雷达", page_title="当前政策信号", intro="这个社会的资源正在往哪里配置，而我应该站到哪里去？", feed=records[:40], highlights=(important or records)[:3], active="home")
    write("policies/index.html", "policy_feed.html", title="全部政策", page_title="全部相关政策", intro="按发布时间连续归档，不制造空白日报。", feed=records, highlights=[], active="policies")
    for topic, slug in TOPIC_SLUGS.items():
        topic_records = [item for item in records if topic in item.get("topics", [])]
        write(f"topics/{slug}/index.html", "policy_feed.html", title=topic, page_title=topic, intro=f"追踪与“{topic}”有关的真实政策变化。", feed=topic_records, highlights=[], active=slug)
    for item in records:
        write(f"policies/{item['id']}/index.html", "policy_detail.html", title=item["title"], policy=item, active="policies", page_description=item.get("analysis", {}).get("one_sentence", "政策原文与结构化解析"))
    write("about/index.html", "policy_about.html", title="关于", active="about")
    assets = output / "assets"
    assets.mkdir()
    for name in ("style.css", "app.js", "favicon.svg"):
        shutil.copy2(template_root / name, assets / name)
    search = [{"id": item["id"], "title": item["title"], "topics": item.get("topics", []), "summary": item.get("analysis", {}).get("one_sentence", ""), "url": f"policies/{item['id']}/"} for item in records]
    (output / "search-index.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
