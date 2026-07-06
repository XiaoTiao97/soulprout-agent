from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

SKILL_FILE_NAME = "SKILL.md"
USER_SKILLS_BASE = os.getenv("USER_SKILLS_BASE", "/home/user_skills")


def get_system_skills_dir() -> Path:
    base = Path(__file__).resolve().parent
    local_dir = base / "skills"
    if local_dir.exists():
        return local_dir
    legacy_dir = base.parent / "mcp-server" / "skills"
    return legacy_dir


def get_user_skills_root(user_id: str) -> Path:
    return Path(USER_SKILLS_BASE) / user_id / "skills"


def _parse_skill_frontmatter(content: str):
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not frontmatter_match:
        return None
    fm = yaml.safe_load(frontmatter_match.group(1))
    if not isinstance(fm, dict):
        return None
    name = fm.get("name")
    description = fm.get("description")
    if name and description:
        return {"name": str(name), "description": str(description)}
    return None


def load_skills_from_subfolders(skills_dir: Path, skill_type: str):
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []
    result = []
    for item in skills_dir.iterdir():
        if not item.is_dir():
            continue
        skill_md = item / SKILL_FILE_NAME
        if not skill_md.exists():
            continue
        try:
            parsed = _parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"))
            if parsed:
                parsed["name"] = item.name
                parsed["type"] = skill_type
                result.append(parsed)
        except Exception:
            continue
    return result


class SkillServer:
    def get_merged_skills(self, user_id: str | None = None):
        merged = load_skills_from_subfolders(get_system_skills_dir(), "system")
        if user_id:
            merged.extend(load_skills_from_subfolders(get_user_skills_root(user_id), "user"))
        return merged

