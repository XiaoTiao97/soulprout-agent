"""
Milvus CRUD 核心服务。

MilvusService 负责：
  1. 维护与 Milvus 的单一异步连接（整个进程共享）。
  2. 按需创建/加载 collection（schema 来自 collections/registry.py）。
  3. 提供 insert / upsert / search / hybrid_search / query / delete 操作。

设计原则：
  - 同一 collection_name 只加载一次；已加载的 collection 缓存在 _loaded_collections。
  - text_field 和 default_output_fields 的元信息从 _collection_meta 缓存中读取。
"""

from typing import Any, Optional, Union
from pymilvus import AsyncMilvusClient, AnnSearchRequest, WeightedRanker

from vdb.core.config import VDBConfig
from vdb.collections.registry import get_schema, COLLECTION_TYPE_CONFIGS
from vdb.services.embedding import EmbeddingService


class MilvusService:
    def __init__(self, config: VDBConfig):
        self._config = config
        self._embedding = EmbeddingService(config)
        self._client: Optional[AsyncMilvusClient] = None

        # 已确认存在并已 load 的 collection 集合
        self._loaded_collections: set[str] = set()
        # collection_name -> {text_field, default_output_fields}
        self._collection_meta: dict[str, dict] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # 连接管理
    # ─────────────────────────────────────────────────────────────────────────

    async def connect(self):
        """建立与 Milvus 的连接（幂等）。"""
        if self._client is None:
            kwargs: dict = {"uri": self._config.milvus_uri}
            if self._config.milvus_token:
                kwargs["token"] = self._config.milvus_token
            self._client = AsyncMilvusClient(**kwargs)

    async def close(self):
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _require_client(self) -> AsyncMilvusClient:
        if self._client is None:
            raise RuntimeError("MilvusService 尚未连接，请先调用 connect()。")
        return self._client

    # ─────────────────────────────────────────────────────────────────────────
    # Collection 管理
    # ─────────────────────────────────────────────────────────────────────────

    async def ensure_collection(
        self,
        collection_name: str,
        collection_type: str = "generic",
    ) -> dict:
        """
        确保指定 collection 存在并已加载。
        若不存在则按 collection_type 的 schema 自动创建并建立索引。

        Returns:
            {"collection_name": ..., "collection_type": ..., "created": bool}
        """
        client = self._require_client()
        created = False

        if collection_name not in self._loaded_collections:
            exists = await client.has_collection(collection_name)
            if not exists:
                schema, text_field, default_output_fields = get_schema(
                    collection_type, self._config.embedding_dim
                )
                await client.create_collection(
                    collection_name=collection_name,
                    schema=schema,
                )
                # 创建索引
                index_params = client.prepare_index_params()
                index_params.add_index(
                    field_name="vector",
                    metric_type="IP",
                    index_type="AUTOINDEX",
                )
                index_params.add_index(
                    field_name="sparse_vector",
                    metric_type="BM25",
                    index_type="SPARSE_INVERTED_INDEX",
                )
                await client.create_index(
                    collection_name=collection_name,
                    index_params=index_params,
                )
                created = True
            else:
                # 从已存在的 collection 推断 text_field（优先用 registry 匹配）
                cfg = COLLECTION_TYPE_CONFIGS.get(collection_type, COLLECTION_TYPE_CONFIGS["generic"])
                text_field = cfg["text_field"]
                default_output_fields = cfg["default_output_fields"]

            await client.load_collection(collection_name)
            self._loaded_collections.add(collection_name)

            # 缓存元信息
            if collection_name not in self._collection_meta:
                cfg = COLLECTION_TYPE_CONFIGS.get(collection_type, COLLECTION_TYPE_CONFIGS["generic"])
                self._collection_meta[collection_name] = {
                    "text_field": cfg["text_field"],
                    "default_output_fields": cfg["default_output_fields"],
                }

        return {
            "collection_name": collection_name,
            "collection_type": collection_type,
            "created": created,
        }

    async def drop_collection(self, collection_name: str) -> dict:
        """删除 collection（危险操作）。"""
        client = self._require_client()
        await client.drop_collection(collection_name)
        self._loaded_collections.discard(collection_name)
        self._collection_meta.pop(collection_name, None)
        return {"collection_name": collection_name, "dropped": True}

    async def collection_stats(self, collection_name: str) -> dict:
        """获取 collection 基本统计信息。"""
        client = self._require_client()
        stats = await client.get_collection_stats(collection_name)
        return stats

    async def list_collections(self) -> list[str]:
        client = self._require_client()
        return await client.list_collections()

    # ─────────────────────────────────────────────────────────────────────────
    # 写操作
    # ─────────────────────────────────────────────────────────────────────────

    def _get_text_field(self, collection_name: str) -> str:
        return self._collection_meta.get(collection_name, {}).get("text_field", "text")

    async def insert(
        self,
        collection_name: str,
        data: Union[dict, list[dict]],
        text_field: Optional[str] = None,
    ) -> dict:
        """
        插入数据。调用方传入的 data 中，text_field 对应的字段值会被自动向量化
        并写入 vector 字段（若 data 中已有 vector 则直接使用）。
        """
        client = self._require_client()
        records = [data] if isinstance(data, dict) else data
        tf = text_field or self._get_text_field(collection_name)
        records = await self._fill_vectors(records, tf)
        result = await client.insert(collection_name=collection_name, data=records)
        return {"insert_count": result.get("insert_count", len(records))}

    async def upsert(
        self,
        collection_name: str,
        data: Union[dict, list[dict]],
        text_field: Optional[str] = None,
    ) -> dict:
        client = self._require_client()
        records = [data] if isinstance(data, dict) else data
        tf = text_field or self._get_text_field(collection_name)
        records = await self._fill_vectors(records, tf)
        result = await client.upsert(collection_name=collection_name, data=records)
        return {"upsert_count": result.get("upsert_count", len(records))}

    async def _fill_vectors(self, records: list[dict], text_field: str) -> list[dict]:
        """对缺少 vector 的记录，根据 text_field 自动补充 embedding。"""
        needs_embed = [r for r in records if "vector" not in r or not r["vector"]]
        if not needs_embed:
            return records

        texts = [r.get(text_field, "") for r in needs_embed]
        embeddings = await self._embedding.embed_many(texts)
        idx = 0
        for r in records:
            if "vector" not in r or not r["vector"]:
                r["vector"] = embeddings[idx]
                idx += 1
        return records

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
        """纯 dense vector 检索。"""
        client = self._require_client()
        output_fields = output_fields or self._collection_meta.get(
            collection_name, {}
        ).get("default_output_fields")
        results = await client.search(
            collection_name=collection_name,
            data=query_vectors,
            limit=limit,
            filter=filter,
            output_fields=output_fields,
        )
        return [[hit.get("entity", hit) for hit in r] for r in results]

    async def hybrid_search(
        self,
        collection_name: str,
        query: str,
        limit: int = 5,
        filter: str = "",
        output_fields: Optional[list[str]] = None,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
    ) -> list[dict]:
        """
        Hybrid Search：dense embedding + BM25 稀疏检索，通过 WeightedRanker 融合。
        """
        client = self._require_client()
        output_fields = output_fields or self._collection_meta.get(
            collection_name, {}
        ).get("default_output_fields")

        embedding = await self._embedding.embed_one(query)

        dense_req = AnnSearchRequest(
            data=[embedding],
            anns_field="vector",
            param={"metric_type": "IP", "params": {"nprobe": 10}},
            limit=limit,
            expr=filter or None,
        )
        sparse_req = AnnSearchRequest(
            data=[query],
            anns_field="sparse_vector",
            param={"metric_type": "BM25"},
            limit=limit,
            expr=filter or None,
        )

        results = await client.hybrid_search(
            collection_name,
            [dense_req, sparse_req],
            WeightedRanker(dense_weight, sparse_weight),
            limit=limit,
            output_fields=output_fields,
        )
        # 将 distance（融合后分数）合并进 entity 返回，便于上层做阈值过滤
        merged: list[dict] = []
        for hit in results[0]:
            entity = dict(hit.get("entity", {}) or {})
            entity["_score"] = hit.get("distance")
            merged.append(entity)
        return merged

    async def query(
        self,
        collection_name: str,
        filter: str = "",
        limit: int = 100,
        output_fields: Optional[list[str]] = None,
    ) -> list[dict]:
        """按条件过滤查询（不做向量检索）。"""
        client = self._require_client()
        output_fields = output_fields or self._collection_meta.get(
            collection_name, {}
        ).get("default_output_fields")
        return await client.query(
            collection_name=collection_name,
            filter=filter,
            limit=limit,
            output_fields=output_fields,
        )

    async def delete(
        self,
        collection_name: str,
        ids: Optional[Union[list, str, int]] = None,
        filter: str = "",
    ) -> dict:
        client = self._require_client()
        result = await client.delete(
            collection_name=collection_name,
            ids=ids,
            filter=filter,
        )
        return {"delete_count": result.get("delete_count", 0)}
