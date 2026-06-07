import asyncio
import json
import os
import re

import aiofiles.os as aio_os
import shortuuid

from agent.kb.database.crud import MongoDBCRUD
from agent.kb.models.kb import (
    ChunkContent,
    ChunkItem,
    ChunkModel,
    DocumentModel,
    LibraryModel,
)
from agent.kb.models.message import UploadFileResponse
from agent.kb.services.agents_box import AgentsBox
from agent.kb.utils.file_process import AsyncFileProcess
from agent.utils.vdb_client import VDBClient


class KBManager:
    def __init__(self, config):
        self.config = config
        self.library_crud = MongoDBCRUD(config.db_libraries)
        self.document_crud = MongoDBCRUD(config.db_documents)
        self.chunk_crud = MongoDBCRUD(config.db_chunks)
        self.agents_box = AgentsBox(config)
        self.file_process = AsyncFileProcess()
        self.vdb_client = VDBClient(
            dense_weight=config.hybrid_search_dense_weight,
            sparse_weight=config.hybrid_search_sparse_weight,
        )
        self.kb_collection = config.kb_collection

    async def _ensure_vdb(self):
        await self.vdb_client.ensure_collection(self.kb_collection, "kb")

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def create_knowledge_base(self, kb_id: str, user_id: str, files):
        try:
            if files:
                async for response in self._process_files_concurrently(user_id, kb_id, files):
                    yield response
            else:
                yield UploadFileResponse(success=False, message="未上传文件").model_dump_json()
        except Exception as e:
            await self.library_crud.delete_one({"kb_id": kb_id})
            yield UploadFileResponse(success=False, message=f"创建知识库失败，失败原因：{e}").model_dump_json()

    async def add_file_to_kb(self, kb_id: str, files, max_concurrency: int = 5):
        library = await self.library_crud.read({"kb_id": kb_id})
        if not library:
            raise Exception(f"知识库 {kb_id} 不存在")
        new_files_number = len(files)
        await self._ensure_vdb()
        try:
            semaphore = asyncio.Semaphore(max_concurrency)

            async def process_with_semaphore(file):
                async with semaphore:
                    return await self._process_single_file(kb_id, file)

            tasks = [process_with_semaphore(file) for file in files]
            for future in asyncio.as_completed(tasks):
                result = await future
                print(result)
                yield UploadFileResponse(**result).model_dump_json()

            current_count = library.get("kb_file_count", 0)
            await self.library_crud.update(
                {"kb_id": kb_id},
                {"kb_file_count": current_count + new_files_number},
            )
        except Exception as e:
            raise Exception(f"添加文件失败: {str(e)}")

    async def delete_knowledge_base(self, kb_id: str):
        library = await self.library_crud.read({"kb_id": kb_id})
        if not library:
            raise Exception(f"知识库 {kb_id} 不存在")

        try:
            documents = await self.document_crud.read_all({"kb_id": kb_id})
            deleted_docs = 0
            for doc in documents:
                success = await self.document_crud.delete_one({"doc_id": doc["doc_id"]})
                if success:
                    deleted_docs += 1
            await self.chunk_crud.delete_many({"kb_id": kb_id})
            library_deleted = await self.library_crud.delete_one({"kb_id": kb_id})

            await self._ensure_vdb()
            kb_id_escaped = self._escape_filter_value(kb_id)
            await self.vdb_client.delete(self.kb_collection, filter=f'kb_id == "{kb_id_escaped}"')

            if library_deleted:
                return {
                    "success": True,
                    "message": f"成功删除知识库 {kb_id} 及其 {deleted_docs} 个文档",
                }
            raise Exception("删除知识库失败")
        except Exception as e:
            raise Exception(f"删除知识库失败: {str(e)}")

    async def delete_document(self, doc_id: str):
        document = await self.document_crud.read({"doc_id": doc_id})
        if not document:
            raise Exception(f"文档 {doc_id} 不存在")

        try:
            success_document = await self.document_crud.delete_one({"doc_id": doc_id})
            await self.chunk_crud.delete_many({"doc_id": doc_id})

            await self._ensure_vdb()
            doc_id_escaped = self._escape_filter_value(doc_id)
            await self.vdb_client.delete(self.kb_collection, filter=f'doc_id == "{doc_id_escaped}"')

            success_local = await self.del_local_doc(
                kb_id=document.get("kb_id"),
                filename=document.get("name"),
            )
            success = success_document and success_local
            if success:
                kb_id = document["kb_id"]
                library = await self.library_crud.read({"kb_id": kb_id})
                if library:
                    current_count = library.get("kb_file_count", 0)
                    await self.library_crud.update(
                        {"kb_id": kb_id},
                        {"kb_file_count": max(0, current_count - 1)},
                    )
                return {"success": True, "message": f"成功删除文档 {doc_id}"}
            raise Exception("删除文档失败")
        except Exception as e:
            raise Exception(f"删除文档失败: {str(e)}")

    async def get_user_knowledge_bases(self, user_id: str):
        try:
            query = {"user_id": user_id} if user_id else {}
            libraries = await self.library_crud.read_all(query)
            return [
                {
                    "kb_id": lib["kb_id"],
                    "kb_name": lib["kb_name"],
                    "kb_name_zh": lib["kb_name_zh"],
                    "kb_description": lib["kb_description"],
                    "kb_file_count": lib.get("kb_file_count", 0),
                }
                for lib in libraries
            ]
        except Exception as e:
            raise Exception(f"获取知识库列表失败: {str(e)}")

    async def get_knowledge_base_documents(self, kb_id: str):
        try:
            projection = {"contents": 0}
            documents = await self.document_crud.read_all({"kb_id": kb_id}, projection=projection)
            return [
                {
                    "doc_id": doc["doc_id"],
                    "name": doc["name"],
                    "description": doc["description"],
                    "kb_id": doc["kb_id"],
                }
                for doc in documents
            ]
        except Exception as e:
            raise Exception(f"获取文档列表失败: {str(e)}")

    async def _process_files_concurrently(self, user_id: str, kb_id: str, files, max_concurrency: int = 5):
        await self._ensure_vdb()
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(file):
            async with semaphore:
                return await self._process_single_file(kb_id, file)

        tasks = [process_with_semaphore(file) for file in files]
        for future in asyncio.as_completed(tasks):
            result = await future
            print(result)
            yield UploadFileResponse(**result).model_dump_json()

        doc_info = await self.get_knowledge_base_documents(kb_id=kb_id)
        if len(doc_info) > 0:
            attempt_n = 0
            response = UploadFileResponse(success=False, message="创建知识库失败，请重试").model_dump_json()
            while attempt_n < 3:
                try:
                    kb_info = await self.agents_box.run(agent="kb_description", input_text=str(doc_info))
                    re_info = re.search(r"```json\n(.*?)\n```", kb_info, re.DOTALL).group(1).strip()
                    kb_info_dict = json.loads(re_info)
                    kb_info_dict = kb_info_dict[0] if isinstance(kb_info_dict, list) else kb_info_dict
                    name_zh = kb_info_dict.get("name_zh")
                    name = kb_info_dict.get("name")
                    description = kb_info_dict.get("description")
                    library_data = LibraryModel(
                        user_id=user_id,
                        kb_id=kb_id,
                        kb_name_zh=name_zh,
                        kb_name=name,
                        kb_description=description,
                        kb_file_count=len(files),
                    )
                    await self.library_crud.create(library_data.model_dump())
                    response = UploadFileResponse(success=True, message="已生成知识库").model_dump_json()
                    break
                except Exception as e:
                    attempt_n += 1
                    response = UploadFileResponse(
                        success=False,
                        message=f"创建知识库失败，失败原因：{e}，正在重试",
                    ).model_dump_json()
                    await asyncio.sleep(0.1)
        else:
            response = UploadFileResponse(success=False, message="创建知识库失败，请重试").model_dump_json()
        yield response

    async def _process_single_file(self, kb_id: str, file):
        doc_id = shortuuid.ShortUUID().random(length=10)
        try:
            file_description, chunk_abstract_list, chunk_content_list = await self._ai_parse_file(file)

            for chunk_content in chunk_content_list:
                chunk_data = ChunkModel(
                    kb_id=kb_id,
                    doc_id=doc_id,
                    **chunk_content.model_dump(),
                )
                await self.chunk_crud.create(chunk_data.model_dump())

            document_data = DocumentModel(
                kb_id=kb_id,
                doc_id=doc_id,
                name=file.file_name,
                description=file_description,
                chunks=chunk_abstract_list,
            )
            await self.document_crud.create(document_data.model_dump())

            chunk_contents = [chunk_content.content for chunk_content in chunk_content_list]
            chunk_ids = [chunk_content.chunk_id for chunk_content in chunk_content_list]
            kb_vdb_data_list = [
                {
                    "content": chunk_contents[i],
                    "kb_id": kb_id,
                    "doc_id": doc_id,
                    "chunk_id": chunk_ids[i],
                }
                for i in range(len(chunk_contents))
            ]
            result = await self.vdb_client.insert(
                self.kb_collection,
                kb_vdb_data_list,
                text_field="content",
            )
            print(f"已存入向量库知识库段落数量: {result.get('insert_count')}")

            return {"success": True, "doc_id": doc_id}
        except Exception as e:
            return {"success": False, "doc_id": doc_id, "message": str(e)}

    async def _ai_parse_file(self, file, max_concurrency: int = 10):
        file_text = await self.file_process.file_parse(file=file)
        file_description = await self.agents_box.run(agent="file_description", input_text=file_text)
        chunk_list = await self.file_process.split_text_by_tokens(text=file_text)
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(chunk_text):
            async with semaphore:
                return await self.agents_box.run(
                    agent="chunk_description",
                    input_text=chunk_text,
                    context=file_description,
                )

        tasks = [process_with_semaphore(chunk_text) for chunk_text in chunk_list]
        chunk_abstract_list = await asyncio.gather(*tasks, return_exceptions=True)
        successful_chunk_abstract_list = []
        successful_chunk_content_list = []

        for i, result in enumerate(chunk_abstract_list):
            chunk_id = shortuuid.ShortUUID().random(length=6)
            if isinstance(result, Exception):
                print(f"文件 {i} 处理失败: {result}")
            else:
                successful_chunk_abstract_list.append(ChunkItem(chunk_id=chunk_id, abstract=result))
                successful_chunk_content_list.append(ChunkContent(chunk_id=chunk_id, content=chunk_list[i]))
        return file_description, successful_chunk_abstract_list, successful_chunk_content_list

    async def update_kb_info(self, kb_id, kb_name_zh, kb_description):
        return await self.library_crud.update(
            query={"kb_id": kb_id},
            update_data={"kb_name_zh": kb_name_zh, "kb_description": kb_description},
        )

    async def del_local_doc(self, kb_id, filename):
        file_path = os.path.join(self.config.kb_file_path, kb_id, filename)
        if await aio_os.path.exists(file_path):
            await aio_os.remove(file_path)
            print(f"已删除文件: {file_path}")

            kb_dir = os.path.join(self.config.kb_file_path, kb_id)
            try:
                is_empty = len(await aio_os.listdir(kb_dir)) == 0
                if is_empty:
                    await aio_os.rmdir(kb_dir)
                    print(f"已删除空目录: {kb_dir}")
                return True
            except Exception as e:
                print(f"检查或删除目录时出错: {e}")
                return False
        return True
