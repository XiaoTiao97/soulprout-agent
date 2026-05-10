from openai import AsyncOpenAI
from zai import ZhipuAiClient

class LLM:
    def __init__(self, config):
        self.config = config
    async def kimi(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.kimi_key, base_url="https://api.moonshot.cn/v1")
        tools = model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **({"tools": tools} if len(tools) > 0 else {}),
            **({"extra_body": {"thinking": {"type": "enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type": "disabled"}}})
        )
        async for chunk in completion:
            yield chunk
    async def deepseek(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.deepseek_key, base_url="https://api.deepseek.com")
        tools = model_config.tools
        if model_config.model == "deepseek-reasoner":
            for tool in tools:
                tool.get("function")["strict"] = True

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            temperature=1.3,
            stream_options={"include_usage": True},
            max_tokens=8192,
            **({"tools": tools} if len(tools) > 0 else {})
        )

        async for chunk in completion:
            yield chunk

    # ERNIE模型
    # apiKey 获取地址： https://console.bce.baidu.com/iam/#/iam/apikey/list
    # 支持的模型列表： https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Fm2vrveyu
    async def ernie_no_stream(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.ernie_key, base_url="https://qianfan.baidubce.com/v2")
        tools = model_config.tools

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            **({"tools": tools} if len(tools) > 0 else {})
        )
        return completion.choices[0].message.content

    async def ark(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.ark_key, base_url="https://ark.cn-beijing.volces.com/api/v3")
        tools = model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=32768,
            **({"tools": tools} if len(tools) > 0 else {}),
            **({"extra_body": {"thinking":{"type":"enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type":"disabled"}}})
        )
        async for chunk in completion:
            yield chunk

    async def ark_no_stream(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.ark_key, base_url="https://ark.cn-beijing.volces.com/api/v3")
        tools = model_config.tools
        del model_config.model_source
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = await client.chat.completions.create(messages=messages, **model_config.model_dump(),
        **({"extra_body": {"thinking":{"type":"enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type":"disabled"}}}))
        return completion.choices[0].message.content

    async def ark_parse(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.ark_key, base_url="https://ark.cn-beijing.volces.com/api/v3")
        del model_config.model_source
        del model_config.stream
        del model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]
        completion = await client.beta.chat.completions.parse(messages=messages, **model_config.model_dump(),
        **({"extra_body": {"thinking":{"type":"enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type":"disabled"}}}))
        return completion.choices[0].message.parsed

    async def dashscope(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.qwen_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        tools = model_config.tools

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            temperature=1,
            **({"tools": tools} if len(tools) > 0 else {})
        )
        async for chunk in completion:
            yield chunk.choices[0].delta

    async def minimax(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.minimax_key, base_url="https://api.minimaxi.com/v1")
        tools = model_config.tools

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            temperature=1,
            extra_body={"reasoning_split": True},
            stream_options={"include_usage": True},
            **({"tools": tools} if len(tools) > 0 else {}),
        )
        async for chunk in completion:
            yield chunk

    async def glm(self, messages, model_config):
        client = ZhipuAiClient(api_key=self.config.glm_key)
        tools = model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            max_tokens=65536,
            **({"tools": tools} if len(tools) > 0 else {}),
            **({"thinking":{"type":"enabled"}} if thinking == True else {"thinking": {"type":"disabled"}})
        )
        for chunk in completion:
            yield chunk

    async def qianfan(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.qianfan_key, base_url="https://qianfan.baidubce.com/v2")
        tools = model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **({"tools": tools} if len(tools) > 0 else {}),
            **({"extra_body": {"thinking": {"type": "enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type": "disabled"}}})
        )
        async for chunk in completion:
            yield chunk

    async def qianfan_no_stream(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.qianfan_key, base_url="https://qianfan.baidubce.com/v2")
        tools = model_config.tools
        del model_config.model_source
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = await client.chat.completions.create(messages=messages, **model_config.model_dump(),
        **({"extra_body": {"thinking":{"type":"enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type":"disabled"}}}))
        return completion.choices[0].message.content

    async def mimo(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.mimo_key, base_url="https://api.xiaomimimo.com/v1")
        tools = model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            stream=True,
            **({"tools": tools} if len(tools) > 0 else {}),
            **({"extra_body": {"thinking":{"type":"enabled"}}} if thinking == True else {"extra_body": {"thinking": {"type":"disabled"}}})
        )
        async for chunk in completion:
            yield chunk