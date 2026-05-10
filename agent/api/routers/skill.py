from fastapi import APIRouter
from pydantic import BaseModel

from agent.core.config import Config
from agent.skill.manager import load_skill_to_workspace
from agent.skill.skill_server import SkillServer

router = APIRouter()
config = Config()
skill_server = SkillServer()


class SkillLoadRequest(BaseModel):
    skills: dict
    conversation_id: str
    user_id: str


@router.get("/skill")
async def get_skill_info(user_id: str | None = None):
    try:
        data = skill_server.get_merged_skills(user_id=user_id)
        return {"success": True, "data": data, "mode": "full_merged"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/skill")
async def load_skill_agent(payload: SkillLoadRequest):
    return await load_skill_to_workspace(
        conversation_id=payload.conversation_id,
        user_id=payload.user_id,
        skills=payload.skills,
        workspace_base=config.local_file_path,
    )

