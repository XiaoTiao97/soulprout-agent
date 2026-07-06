import asyncio
import shutil
from pathlib import Path

from agent.skill.skill_server import get_system_skills_dir, get_user_skills_root


async def load_skill_to_workspace(conversation_id: str, user_id: str, skills: dict, workspace_base: str):
    try:
        if not conversation_id:
            return {"success": False, "error": "conversation_id不能为空"}
        workspace_root = Path(workspace_base) / conversation_id
        workspace_root.mkdir(parents=True, exist_ok=True)

        if skills and skills.get("system"):
            for skill_name in skills["system"]:
                source = get_system_skills_dir() / skill_name
                if not source.is_dir():
                    return {"success": False, "error": f"技能 {skill_name} 不存在"}
                await asyncio.to_thread(shutil.copytree, source, workspace_root / skill_name, dirs_exist_ok=True)

        if skills and skills.get("user"):
            for skill_name in skills["user"]:
                source = get_user_skills_root(user_id) / skill_name
                if not source.is_dir():
                    return {"success": False, "error": f"用户技能 {skill_name} 不存在"}
                await asyncio.to_thread(shutil.copytree, source, workspace_root / skill_name, dirs_exist_ok=True)

        return {"success": True, "data": "加载skills成功", "mode": "full_merged"}
    except Exception as e:
        return {"success": False, "error": str(e)}

