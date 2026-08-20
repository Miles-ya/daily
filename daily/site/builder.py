from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
DOCUMENT_TYPES = {
    "macro_overview": "宏观运行概览", "official_interpretation": "官方解读",
    "press_release": "新闻发布", "ordinary_document": "统计资料",
}


def normalize_base_url(value: str) -> str:
    return "/" if value == "/" else f"/{value.strip('/')}/"


def _parts(value: str) -> dict:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return {"iso": value, "display": parsed.strftime("%Y.%m.%d"), "year": str(parsed.year),
            "month": f"{parsed.month}月", "day": f"{parsed.day:02d}", "weekday": WEEKDAYS[parsed.weekday()]}


def _empty_report(channel: str, value: str) -> dict:
    return {"channel": channel, "date": value, "generated_on": "", "status": "empty", "one_sentence": "",
            "highlights": [], "documents": [], "sections": {}}


def _calendar(report_date: str, reports: dict[str, dict]) -> list[dict]:
    end = datetime.strptime(report_date, "%Y-%m-%d").date()
    known = [datetime.strptime(value, "%Y-%m-%d").date() for value in reports if value]
    start = max(min(known, default=end), end - timedelta(days=366))
    result = []
    current = end
    while current >= start:
        value = current.isoformat()
        result.append({**_parts(value), "report": reports.get(value, _empty_report("economy", value))})
        current -= timedelta(days=1)
    return result


def build_site(root: Path, output: Path, base_url: str, documents: list[dict], events: list[dict], digests: list[dict], metrics: list[dict],
               document_analyses: dict[str, dict] | None = None, report_date: str | None = None) -> None:
    base_url = normalize_base_url(base_url)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    env = Environment(loader=FileSystemLoader(root / "daily/site/templates"), autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.globals["base_url"] = base_url
    env.globals["asset"] = lambda path: base_url + path.lstrip("/")
    env.globals["document_type_name"] = lambda value: DOCUMENT_TYPES.get(value, "统计资料")
    documents_by_id = {document["id"]: document for document in documents}
    document_analyses = document_analyses or {}
    economy_reports = {digest["date"]: digest for digest in digests if digest.get("channel", "economy") == "economy"}
    report_date = report_date or (max(economy_reports) if economy_reports else date.today().isoformat())
    economy_reports.setdefault(report_date, _empty_report("economy", report_date))
    calendar = _calendar(report_date, economy_reports)
    shared = {"documents": documents_by_id, "events": events, "metrics": metrics, "report_date": report_date}

    def write(relative: str, template: str, **values) -> None:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(**shared, **values), encoding="utf-8")

    current_report = economy_reports[report_date]
    root_values = {"title": "今日日报", "channel": "economy", "channel_name": "经济", "report": current_report,
                   "date_info": _parts(report_date), "previous_date": calendar[1]["iso"] if len(calendar) > 1 else None, "next_date": None}
    write("index.html", "day.html", **root_values)
    write("economy/index.html", "day.html", **{**root_values, "title": "经济日报"})
    write("economy/archive/index.html", "channel_archive.html", title="经济日报归档", channel="economy", channel_name="经济", calendar=calendar)
    write("archive/index.html", "channel_archive.html", title="日报归档", channel="economy", channel_name="经济", calendar=calendar)
    write("all/index.html", "channel_archive.html", title="日报归档", channel="economy", channel_name="经济", calendar=calendar)
    write("daily/index.html", "day.html", **root_values)
    for index, item in enumerate(calendar):
        write(f"economy/{item['iso']}/index.html", "day.html", title=f"{item['display']} 经济日报", channel="economy", channel_name="经济",
              report=item["report"], date_info=item,
              previous_date=calendar[index + 1]["iso"] if index + 1 < len(calendar) else None,
              next_date=calendar[index - 1]["iso"] if index > 0 else None)

    ai_report = _empty_report("ai", report_date)
    write("ai/index.html", "day.html", title="AI 日报", channel="ai", channel_name="AI", report=ai_report, date_info=_parts(report_date), previous_date=None, next_date=None)
    write("ai/archive/index.html", "channel_archive.html", title="AI 日报归档", channel="ai", channel_name="AI",
          calendar=[{**_parts(report_date), "report": ai_report}])
    write(f"ai/{report_date}/index.html", "day.html", title=f"{_parts(report_date)['display']} AI 日报", channel="ai", channel_name="AI", report=ai_report, date_info=_parts(report_date), previous_date=None, next_date=None)

    for document in documents:
        analysis = document_analyses.get(document["id"], {}).get("analysis", {})
        values = {"title": document["title"], "channel": document.get("channel", "economy"), "channel_name": "经济",
                  "document": document, "analysis": analysis}
        write(f"economy/documents/{document['id']}/index.html", "document.html", **values)
        write(f"documents/{document['id']}/index.html", "document.html", **values)
    for event in events:
        write(f"events/{event['id']}/index.html", "event.html", title=event["title"], channel="economy", channel_name="经济", event=event)

    write("about/index.html", "about.html", title="关于", channel="economy", channel_name="经济", updated=_parts(report_date)["display"])
    write("hot/index.html", "hot.html", title="当前信号", channel="economy", channel_name="经济")
    write("metrics/index.html", "metrics.html", title="数据指标", channel="economy", channel_name="经济")
    assets = output / "assets"
    assets.mkdir()
    for name in ("style.css", "app.js", "favicon.svg"):
        shutil.copy2(root / "daily/site/templates" / name, assets / name)
    search = [{"id": document["id"], "title": document["title"], "tags": document.get("tags", []),
               "summary": document_analyses.get(document["id"], {}).get("analysis", {}).get("one_sentence", ""),
               "url": f"economy/documents/{document['id']}/"} for document in documents]
    (output / "search-index.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
