"""
Rokid / 灵珠接入（Gateway 侧）。

SSE 由主站 Agent 提供；Gateway 仅负责：
- 展示配置说明与凭证
- 本地生成 API Key 并上传到主站保存
"""

from __future__ import annotations

# 灵珠填写的公网 SSE（主站）
ROKID_PUBLIC_SSE_URL = "https://www.soulprout.com/api/metis/agent/api/sse"
ROKID_SSE_PATH = "/metis/agent/api/sse"
ROKID_HOME_URL = "https://rizon.rokid.com/space/home"
