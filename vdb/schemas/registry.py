"""
Collection Schema 注册表。

每种 collection_type 定义：
  - text_field   : 用于 BM25 分析的主文本字段名
  - fields       : FieldSchema 列表（不含 sparse_vector，由 add_function 自动补充）
  - default_output_fields : hybrid_search / query 默认返回的字段

调用方通过 get_schema(collection_type, embedding_dim) 获取
(CollectionSchema, text_field, default_output_fields)。
"""

from pymilvus import (
    DataType,
    FieldSchema,
    CollectionSchema,
    Function,
    FunctionType,
)

# ─────────────────────────────────────────────────────────────────────────────
# 各 collection_type 的元配置
# ─────────────────────────────────────────────────────────────────────────────

COLLECTION_TYPE_CONFIGS: dict[str, dict] = {
    # 知识库分块存储
    "kb": {
        "text_field": "content",
        "extra_fields": [
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535, enable_analyzer=True),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="kb_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=128),
        ],
        "default_output_fields": ["content", "chunk_id", "kb_id", "doc_id"],
    },

    # MCP 工具 / 技能描述
    "mcp": {
        "text_field": "description",
        "extra_fields": [
            FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=4096, enable_analyzer=True),
            FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="inputSchema", dtype=DataType.VARCHAR, max_length=65535),
        ],
        "default_output_fields": ["name", "description", "inputSchema"],
    },

    # 技能（skill）描述
    "skill": {
        "text_field": "description",
        "extra_fields": [
            FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=4096, enable_analyzer=True),
            FieldSchema(name="skill_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
        ],
        "default_output_fields": ["skill_id", "name", "description", "category"],
    },

    # 记忆条目：description 用于 BM25 检索，content 存储完整记忆原文
    # name 作为记忆的业务唯一标识，由调用方保证（user_id, name）唯一
    "memory": {
        "text_field": "description",
        "extra_fields": [
            FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=2048, enable_analyzer=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="memory_type", dtype=DataType.VARCHAR, max_length=64),
        ],
        "default_output_fields": ["name", "description", "content", "user_id", "memory_type"],
    },

    # 通用类型：只有基础字段 + text，其余存入 dynamic field
    "generic": {
        "text_field": "text",
        "extra_fields": [
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535, enable_analyzer=True),
        ],
        "default_output_fields": ["text"],
    },
}


def get_schema(
    collection_type: str,
    embedding_dim: int = 1536,
) -> tuple[CollectionSchema, str, list[str]]:
    """
    根据 collection_type 构建 Milvus CollectionSchema。

    Returns:
        (schema, text_field_name, default_output_fields)
    """
    cfg = COLLECTION_TYPE_CONFIGS.get(collection_type)
    if cfg is None:
        raise ValueError(
            f"未知的 collection_type: '{collection_type}'。"
            f"可选值: {list(COLLECTION_TYPE_CONFIGS.keys())}"
        )

    text_field: str = cfg["text_field"]
    default_output_fields: list[str] = cfg["default_output_fields"]

    # 基础字段：id + dense vector + sparse vector
    base_fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, auto_id=True, max_length=128),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
        *cfg["extra_fields"],
        FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
    ]

    schema = CollectionSchema(fields=base_fields, enable_dynamic_field=True)

    # 注册 BM25 函数：将 text_field -> sparse_vector
    schema.add_function(Function(
        name="bm25_func",
        input_field_names=[text_field],
        output_field_names=["sparse_vector"],
        function_type=FunctionType.BM25,
    ))

    return schema, text_field, default_output_fields


def list_collection_types() -> list[str]:
    return list(COLLECTION_TYPE_CONFIGS.keys())
