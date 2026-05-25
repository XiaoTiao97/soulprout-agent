import os
import asyncio
import re
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import json
import openpyxl
from alibabacloud_docmind_api20220711 import models as docmind_api20220711_models
from alibabacloud_docmind_api20220711.client import Client as docmind_api20220711Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient


class AsyncFileProcess:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)

    def aliyun_file_parse(self, file, file_extension):
        config = open_api_models.Config(
            access_key_id=os.getenv("ALIYUN_ACCESS_KEY_ID"),
            access_key_secret=os.getenv("ALIYUN_ACCESS_KEY_SECRET"),
        )
        config.endpoint = "docmind-api.cn-hangzhou.aliyuncs.com"
        client = docmind_api20220711Client(config)
        request = docmind_api20220711_models.SubmitDigitalDocStructureJobAdvanceRequest(
            file_url_object=file,
            file_name=f"upload{file_extension}",
            reveal_markdown=True,
        )
        runtime = util_models.RuntimeOptions()
        try:
            response = client.submit_digital_doc_structure_job_advance(request, runtime)
            data = response.body.data
            markdown_str = ""
            for layout in data["layouts"]:
                markdown_str += layout["markdownContent"] + "\n"
            return markdown_str
        except Exception as error:
            UtilClient.assert_as_string(error.message)
            return error.message

    async def aliyun_file_parse_async(self, file, file_extension):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.aliyun_file_parse, file, file_extension)

    async def xlsx_parse(self, file):
        def _parse_xlsx(file_obj):
            if isinstance(file_obj, BytesIO):
                file_obj.seek(0)
            workbook = openpyxl.load_workbook(file_obj)
            sheet = workbook.active
            text = ""
            for row in sheet.iter_rows(values_only=True):
                text += str(row) + "\n"
            workbook.close()
            return text

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _parse_xlsx, file)

    async def txt_parse(self, file):
        if isinstance(file, BytesIO):
            file.seek(0)
            return file.read().decode("utf-8")
        async with aiofiles.open(file, "r", encoding="utf-8") as f:
            return await f.read()

    async def json_parse(self, file):
        if isinstance(file, (str, Path)):
            async with aiofiles.open(file, "r", encoding="utf-8") as f:
                content = await f.read()
                return str(json.loads(content))
        if hasattr(file, "seek"):
            file.seek(0)
        content = file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return str(json.loads(content))

    async def file_parse(self, file):
        file_extension = file.file_extension
        file_bytes = file.file_bytes
        if file_extension in [".pdf", ".docx", ".doc", ".pptx", ".ppt"]:
            return await self.aliyun_file_parse_async(file_bytes, file_extension)
        if file_extension == ".xlsx":
            return await self.xlsx_parse(file_bytes)
        if file_extension == ".json":
            return await self.json_parse(file_bytes)
        return await self.txt_parse(file_bytes)

    async def split_text_by_tokens(self, text, max_tokens=1000, token_method="mixed"):
        async def count_tokens(text_value):
            if token_method == "char":
                return len(text_value)
            if token_method == "word":
                return len(text_value.split())
            if token_method == "mixed":
                chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text_value))
                english_words = len(re.findall(r"[a-zA-Z]+", text_value))
                punctuation = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text_value))
                return chinese_chars + english_words + punctuation * 0.5
            return len(text_value)

        async def split_by_tokens_only(text_value, limit):
            chunks = []
            current_pos = 0
            while current_pos < len(text_value):
                estimated_end = current_pos + limit
                if estimated_end >= len(text_value):
                    chunks.append(text_value[current_pos:])
                    break
                cut_pos = estimated_end
                search_range = min(50, limit // 10)
                for i in range(search_range):
                    if estimated_end - i > current_pos:
                        char = text_value[estimated_end - i]
                        if char in " \n\t，。！？；：":
                            cut_pos = estimated_end - i + 1
                            break
                chunks.append(text_value[current_pos:cut_pos])
                current_pos = cut_pos
            return chunks

        async def recursive_split(text_value, limit, separators):
            if await count_tokens(text_value) <= limit:
                return [text_value]
            if separators:
                current_separator = separators[0]
                remaining_separators = separators[1:]
                parts = text_value.split(current_separator)
                result = []
                current_chunk = ""
                for i, part in enumerate(parts):
                    part_tokens = await count_tokens(part)
                    if part_tokens > limit:
                        if current_chunk:
                            result.extend(await recursive_split(current_chunk, limit, remaining_separators))
                            current_chunk = ""
                        result.extend(await recursive_split(part, limit, remaining_separators))
                    else:
                        potential_chunk = part if i == 0 else current_chunk + current_separator + part
                        if await count_tokens(potential_chunk) <= limit:
                            current_chunk = potential_chunk
                        else:
                            if current_chunk:
                                result.append(current_chunk)
                            current_chunk = part
                if current_chunk:
                    if await count_tokens(current_chunk) <= limit:
                        result.append(current_chunk)
                    else:
                        result.extend(await recursive_split(current_chunk, limit, remaining_separators))
                return result
            return await split_by_tokens_only(text_value, limit)

        result = await recursive_split(text, max_tokens, ["\n\n", "\n"])
        return [chunk.strip() for chunk in result if chunk.strip()]
