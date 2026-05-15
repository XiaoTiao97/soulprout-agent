"""
VDB API 路由。

所有端点均通过 FastAPI 的依赖注入获取 MilvusService 单例（来自 app.state）。

端点列表：
  Collection 管理
    POST   /vdb/collections/ensure          创建或加载 collection
    DELETE /vdb/collections/{name}          删除 collection
    GET    /vdb/collections                 列出所有 collection
    GET    /vdb/collections/{name}/stats    查看统计信息

  数据写入
    POST   /vdb/collections/{name}/insert   插入
    POST   /vdb/collections/{name}/upsert   更新/插入

  数据检索
    POST   /vdb/collections/{name}/search          纯向量检索
    POST   /vdb/collections/{name}/hybrid_search   混合检索
    POST   /vdb/collections/{name}/query           条件过滤查询

  数据删除
    POST   /vdb/collections/{name}/delete   删除（by ids 或 filter）
"""

from typing import Any, Optional, Union
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from vdb.collections.registry import list_collection_types

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 请求 / 响应 Schema
# ─────────────────────────────────────────────────────────────────────────────

class EnsureCollectionRequest(BaseModel):
    collection_name: str
    collection_type: str = Field(
        default="generic",
        description=f"Collection 类型，可选: {list_collection_types()}",
    )


class InsertRequest(BaseModel):
    data: Union[dict[str, Any], list[dict[str, Any]]]
    text_field: Optional[str] = None  # 覆盖 registry 默认的 text_field


class UpsertRequest(BaseModel):
    data: Union[dict[str, Any], list[dict[str, Any]]]
    text_field: Optional[str] = None


class SearchRequest(BaseModel):
    query_vectors: list[list[float]]
    limit: int = 10
    filter: str = ""
    output_fields: Optional[list[str]] = None


class HybridSearchRequest(BaseModel):
    query: str
    limit: int = 5
    filter: str = ""
    output_fields: Optional[list[str]] = None
    dense_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    sparse_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class QueryRequest(BaseModel):
    filter: str = ""
    limit: int = 100
    output_fields: Optional[list[str]] = None


class DeleteRequest(BaseModel):
    ids: Optional[Union[list[str], list[int], str, int]] = None
    filter: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 辅助依赖
# ─────────────────────────────────────────────────────────────────────────────

def get_milvus(request: Request):
    svc = request.app.state.milvus
    if svc is None:
        raise HTTPException(status_code=503, detail="Milvus 服务未就绪")
    return svc


# ─────────────────────────────────────────────────────────────────────────────
# Collection 管理
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/collections/ensure")
async def ensure_collection(body: EnsureCollectionRequest, request: Request):
    """创建（若不存在）并加载 collection。"""
    svc = get_milvus(request)
    result = await svc.ensure_collection(body.collection_name, body.collection_type)
    return result


@router.get("/collections")
async def list_collections(request: Request):
    """列出 Milvus 中所有 collection。"""
    svc = get_milvus(request)
    names = await svc.list_collections()
    return {"collections": names}


@router.get("/collections/{collection_name}/stats")
async def collection_stats(collection_name: str, request: Request):
    """查询指定 collection 的统计信息（行数等）。"""
    svc = get_milvus(request)
    try:
        stats = await svc.collection_stats(collection_name)
        return stats
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/collections/{collection_name}")
async def drop_collection(collection_name: str, request: Request):
    """删除 collection（不可恢复）。"""
    svc = get_milvus(request)
    return await svc.drop_collection(collection_name)


# ─────────────────────────────────────────────────────────────────────────────
# 写操作
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/collections/{collection_name}/insert")
async def insert(collection_name: str, body: InsertRequest, request: Request):
    """
    插入数据。\n
    - `data` 中可以不含 `vector`，服务端会根据 text_field 自动补充 embedding。
    - `text_field` 不填则使用 collection 创建时注册的默认 text_field。
    """
    svc = get_milvus(request)
    try:
        return await svc.insert(collection_name, body.data, body.text_field)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/{collection_name}/upsert")
async def upsert(collection_name: str, body: UpsertRequest, request: Request):
    """更新已有记录或插入新记录（需要数据中包含 id）。"""
    svc = get_milvus(request)
    try:
        return await svc.upsert(collection_name, body.data, body.text_field)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 读操作
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/collections/{collection_name}/search")
async def search(collection_name: str, body: SearchRequest, request: Request):
    """
    纯 dense vector 检索。\n
    调用方需自行提供 `query_vectors`（已向量化的浮点数列表）。
    """
    svc = get_milvus(request)
    try:
        return await svc.search(
            collection_name,
            body.query_vectors,
            body.limit,
            body.filter,
            body.output_fields,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/{collection_name}/hybrid_search")
async def hybrid_search(collection_name: str, body: HybridSearchRequest, request: Request):
    """
    Hybrid Search（embedding + BM25）。\n
    只需传入原始 `query` 文本，服务端自动完成向量化和稀疏检索，再通过 WeightedRanker 融合。
    """
    svc = get_milvus(request)
    try:
        results = await svc.hybrid_search(
            collection_name,
            body.query,
            body.limit,
            body.filter,
            body.output_fields,
            body.dense_weight,
            body.sparse_weight,
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/{collection_name}/query")
async def query(collection_name: str, body: QueryRequest, request: Request):
    """
    条件过滤查询（不做向量检索）。\n
    `filter` 使用 Milvus 表达式语法，如 `"kb_id == 'abc123'"`。
    """
    svc = get_milvus(request)
    try:
        results = await svc.query(
            collection_name,
            body.filter,
            body.limit,
            body.output_fields,
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 删除操作
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/collections/{collection_name}/delete")
async def delete(collection_name: str, body: DeleteRequest, request: Request):
    """
    删除数据。支持两种方式：\n
    - `ids`：按主键 id 列表删除。
    - `filter`：按 Milvus 表达式批量删除，如 `"kb_id == 'abc123'"`。
    """
    svc = get_milvus(request)
    try:
        return await svc.delete(collection_name, body.ids, body.filter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Embedding 接口（便于调试或外部复用）
# ─────────────────────────────────────────────────────────────────────────────

class EmbedRequest(BaseModel):
    text: Union[str, list[str]]


@router.post("/embed")
async def embed(body: EmbedRequest, request: Request):
    """
    调用 embedding 服务，返回向量。\n
    - 传入 str -> 返回单个 list[float]。
    - 传入 list[str] -> 返回 list[list[float]]。
    """
    svc = get_milvus(request)
    try:
        result = await svc._embedding.embed(body.text)
        return {"embedding": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
