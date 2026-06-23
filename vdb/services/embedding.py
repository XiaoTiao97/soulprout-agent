"""
Embedding 服务：统一封装文本向量化逻辑。
支持 siliconflow / dashscope 两种服务商，单条与批量（自动分批，每批 ≤ 10 条）。
"""

import asyncio
from typing import Union

import httpx
from openai import AsyncOpenAI

from vdb.core.config import VDBConfig


class EmbeddingService:
    def __init__(self, config: VDBConfig):
        self._provider = config.embedding_provider
        self._api_key = (
            config.siliconflow_api_key
            if self._provider == "siliconflow"
            else config.dashscope_api_key
        )
        self._base_url = config.embedding_base_url.rstrip("/")
        self._model = config.embedding_model
        self._dim = config.embedding_dim
        self._batch_size = 10

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    async def _embed_siliconflow(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": {"text": text},
                    "model": self._model,
                    "encoding_format": "float",
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

    async def _embed_dashscope_one(self, text: str) -> list[float]:
        client = self._client()
        resp = await client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dim,
            encoding_format="float",
        )
        return resp.data[0].embedding

    async def embed_one(self, text: str) -> list[float]:
        if self._provider == "siliconflow":
            return await self._embed_siliconflow(text)
        return await self._embed_dashscope_one(text)

    async def _embed_dashscope_many(self, texts: list[str]) -> list[list[float]]:
        client = self._client()
        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i: i + self._batch_size]
            resp = await client.embeddings.create(
                model=self._model,
                input=batch,
                dimensions=self._dim,
                encoding_format="float",
            )
            results.extend(item.embedding for item in resp.data)
        return results

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._provider == "siliconflow":
            results: list[list[float]] = []
            for i in range(0, len(texts), self._batch_size):
                batch = texts[i: i + self._batch_size]
                batch_results = await asyncio.gather(
                    *(self._embed_siliconflow(t) for t in batch)
                )
                results.extend(batch_results)
            return results
        return await self._embed_dashscope_many(texts)

    async def embed(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        if isinstance(text, str):
            return await self.embed_one(text)
        if len(text) == 1:
            return [await self.embed_one(text[0])]
        return await self.embed_many(text)
