import os
from dotenv import load_dotenv

load_dotenv()


class VDBConfig:
    def __init__(self):
        # Milvus 连接配置
        self.milvus_uri = os.getenv("MILVUS_URI", "http://localhost:19530")
        self.milvus_token = os.getenv("MILVUS_TOKEN", "")

        # Embedding 服务配置：siliconflow（默认）| dashscope
        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "siliconflow")
        self.siliconflow_api_key = os.getenv("SILICONFLOW_API_KEY", "")
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")

        if self.embedding_provider == "siliconflow":
            _default_base_url = "https://api.siliconflow.cn/v1"
            _default_model = "Qwen/Qwen3-VL-Embedding-8B"
        else:
            _default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            _default_model = "text-embedding-v4"

        self.embedding_base_url = os.getenv("EMBEDDING_BASE_URL", _default_base_url)
        self.embedding_model = os.getenv("EMBEDDING_MODEL", _default_model)
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "1024"))

        # 预设 Collection 名称（可在 .env 中覆盖）
        self.kb_collection = os.getenv("VDB_KB_COLLECTION", "kb_collection")
        self.skill_collection = os.getenv("VDB_SKILL_COLLECTION", "skill_collection")
        self.memory_collection = os.getenv("VDB_MEMORY_COLLECTION", "memory_collection")
        self.mcp_collection = os.getenv("VDB_MCP_COLLECTION", "mcp_collection")

        # 服务端口
        self.port = int(os.getenv("VDB_PORT", "8888"))
        self.host = os.getenv("VDB_HOST", "0.0.0.0")

        # hybrid_search 融合权重：dense=embedding，sparse=BM25（默认 0.7 / 0.3）
        self.hybrid_search_dense_weight = float(os.getenv("HYBRID_SEARCH_DENSE_WEIGHT", "0.7"))
        self.hybrid_search_sparse_weight = float(os.getenv("HYBRID_SEARCH_SPARSE_WEIGHT", "0.3"))
