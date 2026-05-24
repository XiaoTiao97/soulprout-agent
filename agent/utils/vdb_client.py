"""
VDB 服务 HTTP 客户端。

封装对 vdb 服务（默认 http://localhost:8888）的所有调用，
业务代码无需直接依赖 pymilvus，通过此客户端即可完成向量数据库的所有操作。

使用方式：
    from agent.utils.vdb_client import VDBClient

    client = VDBClient()                           # 使用默认地址
    client = VDBClient(base_url="http://vdb:8888") # 自定义地址

    # 确保 collection 存在（幂等）
    await client.ensure_collection("kb_collection", "kb")

    # 插入（自动 embedding）
    await client.insert("kb_collection", {"content": "...", "kb_id": "x", "chunk_id": "c1"})

    # Hybrid Search（只需传原始文本）
    results = await client.hybrid_search("kb_collection", query="如何申请退款", limit=5)

    # 条件查询
    results = await client.query("kb_collection", filter="kb_id == 'x'", output_fields=["content"])

    # 删除
    await client.delete("kb_collection", filter="kb_id == 'x'")
"""

import os
from typing import Any, Optional, Union

import aiohttp


class VDBClient:
    def __init__(self, base_url: Optional[str] = None):
        self._base = (base_url or os.getenv("VDB_BASE_URL", "http://localhost:8888")).rstrip("/")

    # ─────────────────────────────────────────────────────────────────────────
    # 内部请求助手
    # ─────────────────────────────────────────────────────────────────────────

    async def _post(self, path: str, payload: dict) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base}{path}", json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _get(self, path: str) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base}{path}") as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _delete(self, path: str) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.delete(f"{self._base}{path}") as resp:
                resp.raise_for_status()
                return await resp.json()

    # ─────────────────────────────────────────────────────────────────────────
    # Collection 管理
    # ─────────────────────────────────────────────────────────────────────────

    async def ensure_collection(
        self,
        collection_name: str,
        collection_type: str = "generic",
    ) -> dict:
        """创建（若不存在）并加载 collection。collection_type 决定字段 schema。"""
        return await self._post(
            "/vdb/collections/ensure",
            {"collection_name": collection_name, "collection_type": collection_type},
        )

    async def list_collections(self) -> list[str]:
        result = await self._get("/vdb/collections")
        return result.get("collections", [])

    async def collection_stats(self, collection_name: str) -> dict:
        return await self._get(f"/vdb/collections/{collection_name}/stats")

    async def drop_collection(self, collection_name: str) -> dict:
        return await self._delete(f"/vdb/collections/{collection_name}")

    # ─────────────────────────────────────────────────────────────────────────
    # 写操作
    # ─────────────────────────────────────────────────────────────────────────

    async def insert(
        self,
        collection_name: str,
        data: Union[dict, list[dict]],
        text_field: Optional[str] = None,
    ) -> dict:
        """
        插入数据。data 中若不含 `vector`，服务端会自动用 text_field 生成 embedding。
        """
        payload: dict = {"data": data}
        if text_field:
            payload["text_field"] = text_field
        return await self._post(f"/vdb/collections/{collection_name}/insert", payload)

    async def upsert(
        self,
        collection_name: str,
        data: Union[dict, list[dict]],
        text_field: Optional[str] = None,
    ) -> dict:
        payload: dict = {"data": data}
        if text_field:
            payload["text_field"] = text_field
        return await self._post(f"/vdb/collections/{collection_name}/upsert", payload)

    # ─────────────────────────────────────────────────────────────────────────
    # 读操作
    # ─────────────────────────────────────────────────────────────────────────

    async def search(
        self,
        collection_name: str,
        query_vectors: list[list[float]],
        limit: int = 10,
        filter: str = "",
        output_fields: Optional[list[str]] = None,
    ) -> list[list[dict]]:
        """纯向量检索（调用方自行提供已向量化的 query_vectors）。"""
        payload: dict = {"query_vectors": query_vectors, "limit": limit, "filter": filter}
        if output_fields:
            payload["output_fields"] = output_fields
        return await self._post(f"/vdb/collections/{collection_name}/search", payload)

    async def hybrid_search(
        self,
        collection_name: str,
        query: str,
        limit: int = 5,
        filter: str = "",
        output_fields: Optional[list[str]] = None,
        dense_weight: Optional[float] = None,
        sparse_weight: Optional[float] = None,
    ) -> list[dict]:
        """
        Hybrid Search（embedding + BM25）。只需传原始文本，服务端自动向量化并融合检索。
        融合权重可通过 HYBRID_SEARCH_DENSE_WEIGHT / HYBRID_SEARCH_SPARSE_WEIGHT 环境变量配置。
        """
        if dense_weight is None:
            dense_weight = float(os.getenv("HYBRID_SEARCH_DENSE_WEIGHT", "0.7"))
        if sparse_weight is None:
            sparse_weight = float(os.getenv("HYBRID_SEARCH_SPARSE_WEIGHT", "0.3"))
        payload: dict = {
            "query": query,
            "limit": limit,
            "filter": filter,
            "dense_weight": dense_weight,
            "sparse_weight": sparse_weight,
        }
        if output_fields:
            payload["output_fields"] = output_fields
        result = await self._post(f"/vdb/collections/{collection_name}/hybrid_search", payload)
        return result.get("results", [])

    async def query(
        self,
        collection_name: str,
        filter: str = "",
        limit: int = 100,
        output_fields: Optional[list[str]] = None,
    ) -> list[dict]:
        """按条件过滤查询（不做向量检索）。"""
        payload: dict = {"filter": filter, "limit": limit}
        if output_fields:
            payload["output_fields"] = output_fields
        result = await self._post(f"/vdb/collections/{collection_name}/query", payload)
        return result.get("results", [])

    async def delete(
        self,
        collection_name: str,
        ids: Optional[Union[list, str, int]] = None,
        filter: str = "",
    ) -> dict:
        """按 ids 或 filter 删除数据。"""
        payload: dict = {"filter": filter}
        if ids is not None:
            payload["ids"] = ids
        return await self._post(f"/vdb/collections/{collection_name}/delete", payload)

    # ─────────────────────────────────────────────────────────────────────────
    # Embedding（供需要在 agent 侧直接拿向量的场景使用）
    # ─────────────────────────────────────────────────────────────────────────

    async def embed(
        self,
        text: Union[str, list[str]],
    ) -> Union[list[float], list[list[float]]]:
        """调用 vdb 服务的 embedding 接口。"""
        result = await self._post("/vdb/embed", {"text": text})
        return result.get("embedding")
