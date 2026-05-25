import os

from zai import ZhipuAiClient

class AgentsBox:
    def __init__(self, config):
        self.config = config
        self._model = os.getenv("KB_PARSE_MODEL", "glm-4-long")

    async def prompt(self, agent_name):
        prompt_dict = {
            "file_description": "以下文本是一个文件的全部内容，你需要对该文本的结构和主要内容进行概括。要求精简和准确，字数在200字以内",
            "chunk_description": """# Role：你是一个文本分析智能体，根据整篇文章的全局描述（Context），概括当前段落（USER的输入）的核心内容及其在全文中的作用。
            # Context: {context}
            # Format：语言简洁精准，不超过200字""",
            "kb_description": """以下文本是对一个知识库全部内容的概括。你需要根据这些内容，帮我生成该知识库的三个参数信息，分别是:
            {"name_zh": "<中文名称>",
            "name": "<英文名称>",
            "description": "<该知识库的介绍及描述>"}
            示例如下：
            {"name_zh": "产品信息",
            "name": "project_info",
            "description": "该知识库存储了相关产品的信息，当需要查询该产品时使用此知识库"}
            你的输出要严格按照json格式输出""",
        }
        return prompt_dict.get(agent_name)

    async def run(self, agent, input_text, context=None):
        prompt = await self.prompt(agent)
        prompt = prompt.format(context=context) if context else prompt
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": input_text}]
        client = ZhipuAiClient(api_key=self.config.glm_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content
