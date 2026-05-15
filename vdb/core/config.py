import os
from dotenv import load_dotenv

load_dotenv()


class VDBConfig:
    def __init__(self):
        # Milvus 连接配置
        self.milvus_uri = os.getenv("MILVUS_URI", "http://localhost:27017")
        self.milvus_token = os.getenv("MILVUS_TOKEN", "")

        # Embedding 服务配置（通义千问兼容 OpenAI 接口）
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.embedding_base_url = os.getenv(
            "EMBEDDING_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "1536"))

        # 预设 Collection 名称（可在 .env 中覆盖）
        self.kb_collection = os.getenv("VDB_KB_COLLECTION", "kb_collection")
        self.skill_collection = os.getenv("VDB_SKILL_COLLECTION", "skill_collection")
        self.memory_collection = os.getenv("VDB_MEMORY_COLLECTION", "memory_collection")
        self.mcp_collection = os.getenv("VDB_MCP_COLLECTION", "mcp_collection")

        # 服务端口
        self.port = int(os.getenv("VDB_PORT", "8888"))
        self.host = os.getenv("VDB_HOST", "0.0.0.0")
