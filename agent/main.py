import sys
from pathlib import Path

# `python agent/main.py` 只把 agent/ 放进 sys.path，无法解析顶层包 agent；补上仓库根目录
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import uvicorn
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
from agent.database.models.user import UserInfo
from agent.database.crud.agent_card import update_or_create_agent_card_by_agent_id
from agent.database.models.agent_card import AgentCard
from agent.database.models.agent_subscription import AgentSub
from agent.database.models.conversation import Conversation, COTConversation, SubAgentConversation
from agent.database.models.message import AgentMessage, COTMessage, SubAgentMessage
from agent.database.models.rokid_credential import RokidCredential
from agent.core.config import Config
from agent.skill.skill_indexer import init_skill_collection
from agent.utils.vdb_client import VDBClient
from contextlib import asynccontextmanager
from agent.api.routers import router as api_router

config = Config()

# Use lifespan for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
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
        ],
    )
    for agent_card in [config.kb_agent_card(), *config.default_agent_cards()]:
        await update_or_create_agent_card_by_agent_id(
            AgentCard(**agent_card.model_dump(exclude_unset=True))
        )

    try:
        count = await init_skill_collection()
        print(f"系统技能向量化完成: 共 {count} 条")
    except Exception as e:
        print(f"系统技能向量化失败: {e}")

    try:
        await VDBClient().ensure_collection(config.kb_collection, "kb")
        print(f"知识库向量 collection 就绪: {config.kb_collection}")
    except Exception as e:
        print(f"知识库向量 collection 初始化失败: {e}")

    yield  # Keep the app running
    # Shutdown event (if needed, you can add cleanup here)
    client.close()

# Set the lifespan for the app
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)
