import asyncio
from io import BytesIO
from pdfminer.high_level import extract_text
from docx import Document
import openpyxl
import json
import dashscope
from http import HTTPStatus
from pathlib import Path
import re
import aiofiles
from concurrent.futures import ThreadPoolExecutor
from .pptx_process import extract_ppt_complete_info
from alibabacloud_docmind_api20220711.client import Client as docmind_api20220711Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_docmind_api20220711 import models as docmind_api20220711_models
from alibabacloud_tea_util.client import Client as UtilClient
from alibabacloud_tea_util import models as util_models
import os


class AsyncFileProcess:
    def __init__(self):
        # 创建线程池用于CPU密集型任务
        self.executor = ThreadPoolExecutor(max_workers=4)

    def aliyun_file_parse(self, file):
        config = open_api_models.Config(
            # 通过credentials获取配置中的AccessKey ID
            access_key_id=os.getenv("ALIYUN_ACCESS_KEY_ID"),
            # 通过credentials获取配置中的AccessKey Secret
            access_key_secret=os.getenv("ALIYUN_ACCESS_KEY_SECRET"),
        )
        # 访问的域名
        config.endpoint = f'docmind-api.cn-hangzhou.aliyuncs.com'
        client = docmind_api20220711Client(config)
        request = docmind_api20220711_models.SubmitDigitalDocStructureJobAdvanceRequest(
            # file_url_object : 本地文件流
            file_url_object=open(file, "rb"),
            # file_name ：文件名称。名称必须包含文件类型
            file_name=file,
            reveal_markdown=True,
            # file_name_extension : 文件后缀格式。与文件名二选一
            # file_name_extension='xlsx'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            response = client.submit_digital_doc_structure_job_advance(request, runtime)
            # API返回值格式层级为 body -> data -> 具体属性。
            data = response.body.data
            markdown_str = ""
            for layout in data["layouts"]:
                markdown_str += layout["markdownContent"] + "\n"
            print(markdown_str)
            return markdown_str
        except Exception as error:
            # 如有需要，请打印 error
            UtilClient.assert_as_string(error.message)
            return error.message

    async def aliyun_file_parse_async(self, file):
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(self.executor, self.aliyun_file_parse, file)
        return text

    async def pdf_parse(self, file):
        """异步解析PDF文件"""
        print(file)
        # PDF解析是CPU密集型任务，放到线程池中执行
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(self.executor, extract_text, file)
        return text

    async def docx_parse(self, file):
        """异步解析DOCX文件"""

        def _parse_docx(file_path):
            doc = Document(file_path)
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            return text

        # DOCX解析是CPU密集型任务，放到线程池中执行
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(self.executor, _parse_docx, file)
        return text

    async def xlsx_parse(self, file):
        """异步解析XLSX文件"""

        def _parse_xlsx(file_obj):
            if isinstance(file_obj, BytesIO):
                file_obj.seek(0)  # 重置流指针到开头
            workbook = openpyxl.load_workbook(file_obj)
            sheet = workbook.active
            text = ''
            for row in sheet.iter_rows(values_only=True):
                text += str(row) + '\n'
            workbook.close()
            return text

        # Excel解析是CPU密集型任务，放到线程池中执行
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(self.executor, _parse_xlsx, file)
        return text

    async def txt_parse(self, file):
        """异步解析TXT文件"""
        if isinstance(file, BytesIO):
            # 如果是BytesIO对象，直接读取
            file.seek(0)
            text = file.read().decode('utf-8')
            return text
        else:
            # 如果是文件路径，使用aiofiles异步读取
            async with aiofiles.open(file, 'r', encoding='utf-8') as f:
                text = await f.read()
            return text

    async def json_parse(self, file):
        """异步解析JSON文件"""
        if isinstance(file, (str, Path)):
            # 文件路径，使用aiofiles异步读取
            async with aiofiles.open(file, 'r', encoding='utf-8') as f:
                content = await f.read()
                text = str(json.loads(content))
        else:
            # BytesIO对象或其他
            if hasattr(file, 'seek'):
                file.seek(0)
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            text = str(json.loads(content))
        return text

    async def pptx_parse(self, file):
        """异步解析PDF文件"""
        print(file)
        # PDF解析是CPU密集型任务，放到线程池中执行
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(self.executor, extract_ppt_complete_info, file)
        return text

    def embed_with_qwen(self, text_list):
        dashscope.api_key = 'sk-23367ada9faf462eb6b8ce668598067d'
        embedding_list = []
        for text in text_list:
            resp = dashscope.TextEmbedding.call(
                model=dashscope.TextEmbedding.Models.text_embedding_v2,
                input=text)
            if resp.status_code == HTTPStatus.OK:
                embedding = resp.output['embeddings'][0]['embedding']
                embedding_list.append(embedding)
            else:
                print(resp)
                return resp
        return embedding_list

    async def file_parse(self, file_name, file_bytes):
        text = ""
        if file_name.endswith('.pdf'):
            text = await self.aliyun_file_parse_async(file_bytes)
        elif file_name.endswith('.docx') or file_name.endswith('.doc'):
            text = await self.aliyun_file_parse_async(file_bytes)
        elif file_name.endswith('.xlsx'):
            text = await self.xlsx_parse(file_bytes)
        elif file_name.endswith('.txt'):
            text = await self.txt_parse(file_bytes)
        elif file_name.endswith('.json'):
            text = await self.json_parse(file_bytes)
        elif file_name.endswith('.pptx'):
            text = await self.pptx_parse(file_bytes)
        return text

    async def split_text_by_tokens(self, text, max_tokens=1000, token_method="mixed"):
        """
        按照token数量智能拆分文本，保持原有顺序

        Args:
            text (str): 输入的长文本
            max_tokens (int): 每段的最大token数量，默认1000
            token_method (str): token计算方法
                - "char": 按字符数计算（最简单）
                - "word": 按单词数计算（英文友好）
                - "mixed": 中英文混合计算（推荐）
                - "tiktoken": 使用tiktoken库（需要安装）

        Returns:
            list: 拆分后的文本段落列表
        """

        async def count_tokens(text):
            """根据选择的方法计算token数量"""
            if token_method == "char":
                # 按字符数计算，最简单
                return len(text)

            elif token_method == "word":
                # 按单词数计算，适合英文
                return len(text.split())

            elif token_method == "mixed":
                # 中英文混合计算（推荐）
                # 中文字符按1个token，英文单词按1个token，标点按0.5个token
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
                english_words = len(re.findall(r'[a-zA-Z]+', text))
                punctuation = len(re.findall(r'[^\w\s\u4e00-\u9fff]', text))
                return chinese_chars + english_words + punctuation * 0.5

            elif token_method == "tiktoken":
                # 使用tiktoken库（需要安装）
                try:
                    import tiktoken
                    # 将tiktoken编码操作放在executor中执行，避免阻塞
                    loop = asyncio.get_event_loop()
                    encoding = await loop.run_in_executor(None, tiktoken.get_encoding, "cl100k_base")
                    tokens = await loop.run_in_executor(None, encoding.encode, text)
                    return len(tokens)
                except ImportError:
                    print("tiktoken未安装，自动切换到mixed方法")
                    return await count_tokens_mixed(text)

            else:
                # 默认使用字符数
                return len(text)

        async def count_tokens_mixed(text):
            """中英文混合计算的辅助函数"""
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
            english_words = len(re.findall(r'[a-zA-Z]+', text))
            punctuation = len(re.findall(r'[^\w\s\u4e00-\u9fff]', text))
            return chinese_chars + english_words + punctuation * 0.5

        async def split_by_tokens_only(text, max_tokens):
            """直接按token数量拆分文本"""
            if token_method == "tiktoken":
                try:
                    import tiktoken
                    loop = asyncio.get_event_loop()
                    encoding = await loop.run_in_executor(None, tiktoken.get_encoding, "cl100k_base")
                    tokens = await loop.run_in_executor(None, encoding.encode, text)
                    chunks = []

                    for i in range(0, len(tokens), max_tokens):
                        chunk_tokens = tokens[i:i + max_tokens]
                        # 将解码操作也放在executor中执行
                        chunk_text = await loop.run_in_executor(None, encoding.decode, chunk_tokens)
                        chunks.append(chunk_text)

                    return chunks
                except ImportError:
                    # 如果tiktoken不可用，使用字符切分
                    pass

            # 非tiktoken方法，使用字符切分
            chunks = []
            current_pos = 0

            while current_pos < len(text):
                # 估算切分点
                estimated_end = current_pos + max_tokens

                if estimated_end >= len(text):
                    chunks.append(text[current_pos:])
                    break

                # 寻找合适的切分点，避免切断单词
                cut_pos = estimated_end

                # 尝试在附近找到空格或标点
                search_range = min(50, max_tokens // 10)  # 搜索范围
                for i in range(search_range):
                    if estimated_end - i > current_pos:
                        char = text[estimated_end - i]
                        if char in ' \n\t，。！？；：':
                            cut_pos = estimated_end - i + 1
                            break

                chunks.append(text[current_pos:cut_pos])
                current_pos = cut_pos

            return chunks

        async def recursive_split(text, max_tokens, separators):
            """递归拆分文本"""
            # 如果文本token数量已经小于等于限制，直接返回
            if await count_tokens(text) <= max_tokens:
                return [text]

            # 如果还有分隔符可以使用
            if separators:
                current_separator = separators[0]
                remaining_separators = separators[1:]

                # 按当前分隔符拆分
                parts = text.split(current_separator)

                result = []
                current_chunk = ""

                for i, part in enumerate(parts):
                    # 如果当前部分本身就超过限制，需要进一步拆分
                    part_tokens = await count_tokens(part)
                    if part_tokens > max_tokens:
                        # 先处理之前累积的chunk
                        if current_chunk:
                            sub_chunks = await recursive_split(current_chunk, max_tokens, remaining_separators)
                            result.extend(sub_chunks)
                            current_chunk = ""

                        # 递归处理当前超长部分
                        sub_chunks = await recursive_split(part, max_tokens, remaining_separators)
                        result.extend(sub_chunks)
                    else:
                        # 尝试将当前部分加入chunk
                        if i == 0:
                            potential_chunk = part
                        else:
                            potential_chunk = current_chunk + current_separator + part

                        # 如果加入后不超过限制，则加入
                        potential_tokens = await count_tokens(potential_chunk)
                        if potential_tokens <= max_tokens:
                            current_chunk = potential_chunk
                        else:
                            # 如果加入后超过限制，先保存之前的chunk
                            if current_chunk:
                                result.append(current_chunk)
                            current_chunk = part

                # 处理最后剩余的chunk
                if current_chunk:
                    current_tokens = await count_tokens(current_chunk)
                    if current_tokens <= max_tokens:
                        result.append(current_chunk)
                    else:
                        sub_chunks = await recursive_split(current_chunk, max_tokens, remaining_separators)
                        result.extend(sub_chunks)

                return result

            # 如果没有分隔符了，直接按token拆分
            else:
                return await split_by_tokens_only(text, max_tokens)

        # 定义分隔符优先级：先按段落，再按行，最后按token
        separators = ["\n\n", "\n"]

        # 开始递归拆分
        result = await recursive_split(text, max_tokens, separators)

        # 过滤掉空字符串
        result = [chunk.strip() for chunk in result if chunk.strip()]

        return result
