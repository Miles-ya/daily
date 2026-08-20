from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from daily.runner import run_pipeline
from daily.policy_runner import build_policy_output, run_policy_pipeline
from daily.notifications.policy import notify_policies


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="daily", description="Policy Radar intelligence pipeline")
    result.add_argument("command", choices=["policy", "policy-build", "policy-notify", "pipeline", "crawl", "build"], nargs="?", default="policy")
    result.add_argument("--date")
    result.add_argument("--channel", default="economy", choices=["economy"])
    result.add_argument("--offline", action="store_true", help="使用已保存数据，不联网抓取")
    result.add_argument("--no-ai", action="store_true")
    result.add_argument("--url", action="append", default=[])
    result.add_argument("--max-documents", type=int)
    result.add_argument("--root", type=Path, default=Path.cwd())
    result.add_argument("--policy-ids", default="", help="逗号分隔的政策 ID，仅用于 Telegram 推送")
    result.add_argument("--site-url", default="https://miles-ya.github.io/daily/")
    result.add_argument("--result-file", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = args.root.resolve()
    if args.command == "policy":
        result = run_policy_pipeline(root, online=not args.offline, enable_ai=not args.no_ai)
    elif args.command == "policy-build":
        result = build_policy_output(root)
    elif args.command == "policy-notify":
        result = notify_policies(root, [value for value in args.policy_ids.split(",") if value], args.site_url)
    else:
        offline = args.offline or args.command == "build"
        result = run_pipeline(root, args.date, not offline, not args.no_ai, args.url or None, args.max_documents)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_file:
        args.result_file.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
