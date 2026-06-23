"""DuckDuckGo / ddgs 联网检索测试脚本。

依赖安装:
    pip install ddgs

用法:
    python duckducktest.py
    python duckducktest.py "Python asyncio 教程"
    python duckducktest.py "最新 AI 新闻" -n 5
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from ddgs import DDGS
except ImportError:
    print("缺少依赖，请先执行: pip install ddgs", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="DuckDuckGo 联网检索测试")
    parser.add_argument("query", nargs="?", default="Python asyncio tutorial")
    parser.add_argument("-n", "--count", type=int, default=10)
    args = parser.parse_args()

    backends = ("duckduckgo", "brave", "mojeek", "startpage")
    results = []
    last_error = None

    with DDGS() as ddgs:
        for backend in backends:
            try:
                raw = ddgs.text(args.query, max_results=args.count, backend=backend)
                if raw:
                    results = [
                        {
                            "title": item.get("title") or "",
                            "link": item.get("href") or item.get("link") or "",
                            "content": item.get("body") or item.get("snippet") or "",
                            "media": item.get("source") or "",
                            "publish_date": item.get("date") or "",
                        }
                        for item in raw
                    ]
                    print(f"命中后端: {backend}", file=sys.stderr)
                    break
            except Exception as exc:
                last_error = exc

    if not results:
        print(f"搜索失败: {last_error}", file=sys.stderr)
        sys.exit(1)

    print(f"搜索关键词: {args.query}")
    print(f"结果数量: {len(results)}\n")
    for index, item in enumerate(results, start=1):
        print(f"[{index}] {item['title']}")
        print(f"    链接: {item['link']}")
        print(f"    摘要: {item['content'][:200]}")
        print()
    print("--- JSON 输出 ---")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
