import logging
import os
import sys
from pathlib import Path

# `python agent/main.py` 只把 agent/ 放进 sys.path，无法解析顶层包 agent；补上仓库根目录
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import uvicorn
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from agent.database.models.user import UserInfo
from agent.database.crud.agent_card import update_or_create_agent_card_by_agent_id
from agent.database.models.agent_card import AgentCard
from agent.database.models.agent_subscription import AgentSub
from agent.database.models.conversation import Conversation, COTConversation, SubAgentConversation
from agent.database.models.message import AgentMessage, COTMessage, SubAgentMessage
from agent.database.models.rokid_credential import RokidCredential
from agent.database.models.scheduled_task import ScheduledTask
from agent.database.models.outbound_delivery import OutboundDelivery
from agent.database.models.user_channel_binding import UserChannelBinding
from agent.core.config import Config
from agent.core.logging_setup import bind_user_id, reset_user_id, setup_logging

setup_logging()

from agent.utils.jwt_utils import verify_token
from agent.skill.skill_indexer import init_skill_collection
from agent.utils.vdb_client import VDBClient
from contextlib import asynccontextmanager
from agent.api.routers import router as api_router
import asyncio

logger = logging.getLogger(__name__)

config = Config()


def _request_user_id(request: Request) -> str | None:
    """从 Cookie 或 Bearer 里取出 user_id。无效 token 不当成错误。"""
    token = request.cookies.get("token")
    if not token:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        return None
    try:
        payload = verify_token(token)
    except Exception:
        return None
    if not payload or not payload.get("user_id"):
        return None
    return str(payload["user_id"])

# Use lifespan for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn 可能在导入之后才配置自己的 logger，这里再收编一次。
    setup_logging()
    # Startup event
    client = AsyncIOMotorClient(config.mongodb_url)
    await init_beanie(
        database=client[config.mongodb_database],
        document_models=[
            UserInfo,
            Conversation,
            AgentMessage,
            COTMessage,
            COTConversation,
            SubAgentMessage,
            SubAgentConversation,
            AgentCard,
            AgentSub,
            RokidCredential,
            ScheduledTask,
            OutboundDelivery,
            UserChannelBinding,
        ],
    )
    for agent_card in [config.kb_agent_card(), *config.default_agent_cards()]:
        await update_or_create_agent_card_by_agent_id(
            AgentCard(**agent_card.model_dump(exclude_unset=True))
        )

    try:
        count = await init_skill_collection()
        logger.info("系统技能向量化完成: 共 %s 条", count)
    except Exception:
        logger.exception("系统技能向量化失败")

    try:
        await VDBClient().ensure_collection(config.kb_collection, "kb")
        logger.info("知识库向量 collection 就绪: %s", config.kb_collection)
    except Exception:
        logger.exception("知识库向量 collection 初始化失败")

    scheduler_task = asyncio.create_task(
        _run_scheduler(),
        name="scheduled-task-loop",
    )

    yield  # Keep the app running
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    # Shutdown event (if needed, you can add cleanup here)
    client.close()


async def _run_scheduler():
    from agent.services.scheduler import run_scheduler_loop
    await run_scheduler_loop()

# Set the lifespan for the app
app = FastAPI(lifespan=lifespan)

# 仅放行 App（Capacitor WebView）的来源，用 Authorization 头鉴权，所以不开 credentials。
# 网页端与官网同源、网关是服务端调用，都不受此影响。可用环境变量 CORS_ALLOW_ORIGINS（逗号分隔）覆盖。
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ALLOW_ORIGINS", "https://localhost,http://localhost,capacitor://localhost").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)
app.include_router(api_router)


@app.middleware("http")
async def bind_log_user(request: Request, call_next):
    token = bind_user_id(_request_user_id(request))
    try:
        return await call_next(request)
    finally:
        reset_user_id(token)


if __name__ == '__main__':
    setup_logging()
    # 不再让 uvicorn 用自己的 dictConfig 盖掉上面的 handler。
    uvicorn.run(app, host='0.0.0.0', port=8080, log_config=None)
