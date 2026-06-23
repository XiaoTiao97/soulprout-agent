from openai import AsyncOpenAI

class LLM:
    def __init__(self, config):
        self.config = config

    async def chat(self, messages, model_config):
        key_attr = model_config.model_source + "_key"
        url_attr = model_config.model_source + "_base_url"
        client = AsyncOpenAI(api_key=getattr(self.config, key_attr), base_url=getattr(self.config, url_attr))
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
            **({"extra_body": {"thinking": {"type": "enabled"}}} if thinking else {"extra_body": {"thinking": {"type": "disabled"}}}),
        )
        async for chunk in completion:
            yield chunk

    async def chat_no_stream(self, messages, model_config):
        source = model_config.model_source.removesuffix("_no_stream")
        key_attr = source + "_key"
        url_attr = source + "_base_url"
        client = AsyncOpenAI(api_key=getattr(self.config, key_attr), base_url=getattr(self.config, url_attr))
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]

        del model_config.model_source
        completion = await client.chat.completions.create(
            messages=messages,
            **model_config.model_dump(),
            **({"extra_body": {"thinking": {"type": "enabled"}}} if thinking else {"extra_body": {"thinking": {"type": "disabled"}}}),
        )
        return completion.choices[0].message.content

    async def ernie_no_stream(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.ernie_key, base_url="https://qianfan.baidubce.com/v2")
        tools = model_config.tools

        completion = await client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            **({"tools": tools} if len(tools) > 0 else {}),
        )
        return completion.choices[0].message.content

    async def ark_parse(self, messages, model_config):
        client = AsyncOpenAI(api_key=self.config.ark_key, base_url=self.config.ark_base_url)
        del model_config.model_source
        del model_config.stream
        del model_config.tools
        thinking = False
        if model_config.model.endswith("-thinking"):
            thinking = True
            model_config.model = model_config.model.split("-thinking")[0]
        completion = await client.beta.chat.completions.parse(
            messages=messages,
            **model_config.model_dump(),
            **({"extra_body": {"thinking": {"type": "enabled"}}} if thinking else {"extra_body": {"thinking": {"type": "disabled"}}}),
        )
        return completion.choices[0].message.parsed

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
