# api/__init__.py
from fastapi import APIRouter
from .user import router as auth_router
from .conversation import router as conversation_router
from .message import router as message_router
from .tools import router as tools_router
from .skill import router as skill_router
from .agent_card import router as agent_card_router
from .agent_subscription import router as agent_subscription_router
from agent.kb.router import router as kb_router
from .asr import router as asr_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(conversation_router)
router.include_router(message_router)
router.include_router(tools_router)
router.include_router(skill_router)
router.include_router(agent_card_router)
router.include_router(agent_subscription_router)
router.include_router(kb_router)
router.include_router(asr_router)
