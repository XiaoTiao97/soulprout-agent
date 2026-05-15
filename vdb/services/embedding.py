"""
Embedding 服务：统一封装文本向量化逻辑。
支持单条文本和批量文本（自动分批，每批 ≤ 10 条）。
"""

from typing import Union
from openai import AsyncOpenAI
from vdb.core.config import VDBConfig


class EmbeddingService:
    def __init__(self, config: VDBConfig):
        self._api_key = config.dashscope_api_key
        self._base_url = config.embedding_base_url
        self._model = config.embedding_model
        self._dim = config.embedding_dim
        self._batch_size = 10

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    async def embed_one(self, text: str) -> list[float]:
        """对单条文本生成 embedding。"""
        client = self._client()
        resp = await client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dim,
            encoding_format="float",
        )
        return resp.data[0].embedding

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """对文本列表批量生成 embedding（自动分批）。"""
        if not texts:
            return []

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

    async def embed(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        """
        通用入口：
          - 传入 str   -> 返回 list[float]
          - 传入 list  -> 返回 list[list[float]]
        """
        if isinstance(text, str):
            return await self.embed_one(text)
        if len(text) == 1:
            return [await self.embed_one(text[0])]
        return await self.embed_many(text)
