"""
系统 skill 向量索引初始化。

启动阶段：
    - 扫描 agent/skill/skills/ 下所有内置 skill
    - 以子文件夹名为 skill 标识，description 取自 SKILL.md frontmatter
    - 写入 vdb 的 skill_collection
    - 后续 skills(module=search) 工具通过 description 的 hybrid_search 召回

用户技能（个人 skill）不入向量库——按要求每次直接列举返回。
"""

from __future__ import annotations

import os

from agent.skill.skill_server import get_system_skills_dir, load_skills_from_subfolders
from agent.utils.vdb_client import VDBClient

SKILL_COLLECTION = os.getenv("VDB_SKILL_COLLECTION", "skill_collection")


async def init_skill_collection(reset: bool = True) -> int:
    """
    将所有系统 skill 写入向量库。

    Args:
        reset: True 时先 drop 再重建，确保索引与磁盘 skill 完全一致。

    Returns:
        实际写入的 skill 数量。
    """
    skills = load_skills_from_subfolders(get_system_skills_dir(), "system")
    client = VDBClient()

    if reset:
        try:
            await client.drop_collection(SKILL_COLLECTION)
        except Exception:
            # collection 不存在或 vdb 暂未就绪都允许继续走 ensure_collection
            pass

    await client.ensure_collection(SKILL_COLLECTION, "skill")

    if not skills:
        return 0

    records = []
    for item in skills:
        name = (item.get("name") or "").strip()
        description = (item.get("description") or "").strip()
        if not name or not description:
            continue
        records.append({
            "name": name,
            "description": description,
            "skill_id": name,
            "category": "system",
        })

    if not records:
        return 0

    await client.insert(SKILL_COLLECTION, records)
    return len(records)
