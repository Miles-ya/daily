from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from daily.runner import run_pipeline


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="daily", description="Daily information intelligence pipeline")
    result.add_argument("command", choices=["pipeline", "crawl", "build"], nargs="?", default="pipeline")
    result.add_argument("--date")
    result.add_argument("--channel", default="economy", choices=["economy"])
    result.add_argument("--offline", action="store_true", help="使用已保存数据，不联网抓取")
    result.add_argument("--no-ai", action="store_true")
    result.add_argument("--url", action="append", default=[])
    result.add_argument("--max-documents", type=int)
    result.add_argument("--root", type=Path, default=Path.cwd())
    return result


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    offline = args.offline or args.command == "build"
    result = run_pipeline(args.root.resolve(), args.date, not offline, not args.no_ai, args.url or None, args.max_documents)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
