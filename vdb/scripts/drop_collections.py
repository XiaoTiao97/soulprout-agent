"""
删除 Milvus collection，用于重建 COSINE 索引。

用法（在仓库根目录执行）：
    python vdb/scripts/drop_collections.py --yes
    python vdb/scripts/drop_collections.py --yes --names memory_collection kb_collection
    python vdb/scripts/drop_collections.py --yes --all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from vdb.core.config import VDBConfig
from vdb.services.milvus import MilvusService


def _default_collection_names(config: VDBConfig) -> list[str]:
    return [
        config.kb_collection,
        config.skill_collection,
        config.memory_collection,
        config.mcp_collection,
    ]


async def _run(args: argparse.Namespace) -> int:
    config = VDBConfig()
    svc = MilvusService(config)
    await svc.connect()

    try:
        existing = set(await svc.list_collections())

        if args.all:
            targets = sorted(existing)
        elif args.names:
            targets = args.names
        else:
            targets = _default_collection_names(config)

        if not targets:
            print("没有需要删除的 collection。")
            return 0

        print("Milvus URI:", config.milvus_uri)
        print("当前已有 collection:", sorted(existing) or "(无)")
        print("计划删除:")
        for name in targets:
            status = "存在" if name in existing else "不存在（跳过）"
            print(f"  - {name} ({status})")

        if not args.yes:
            print("\n这是危险操作，会永久删除向量数据。")
            print("确认后请加 --yes 再执行，例如：")
            print("  python vdb/scripts/drop_collections.py --yes")
            return 1

        dropped: list[str] = []
        skipped: list[str] = []
        for name in targets:
            if name not in existing:
                skipped.append(name)
                continue
            await svc.drop_collection(name)
            dropped.append(name)
            print(f"已删除: {name}")

        remaining = await svc.list_collections()
        print("\n完成。")
        print("已删除:", dropped or "(无)")
        print("未找到已跳过:", skipped or "(无)")
        print("剩余 collection:", sorted(remaining) or "(无)")
        print("\n下一步：重启 vdb 服务后重新写入数据，新 collection 会使用 COSINE 索引。")
        return 0
    finally:
        await svc.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="删除 Milvus collection（用于重建 COSINE 索引）")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="确认执行删除（不加此参数仅预览）",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="删除 Milvus 中所有 collection（危险）",
    )
    parser.add_argument(
        "--names",
        nargs="+",
        help="指定要删除的 collection 名称，默认删除 kb/skill/memory/mcp 四个预设 collection",
    )
    args = parser.parse_args()

    if args.all and args.names:
        parser.error("--all 与 --names 不能同时使用")

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
