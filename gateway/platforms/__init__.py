"""
Gateway 平台适配器模块。

已支持平台：
- weixin  个人微信（基于腾讯 iLink Bot API，扫码登录）
- feishu  飞书 / Lark（WebSocket 长连接，扫码或 App ID 配置）
- wecom   企业微信 AI Bot（WebSocket 长连接，扫码或 Bot ID 配置）

飞书 / 企业微信实现参考：https://github.com/NousResearch/hermes-agent
"""

from gateway.platforms.feishu import FeishuAdapter, FeishuQRSession
from gateway.platforms.wecom import WecomAdapter, WecomQRSession
from gateway.platforms.weixin import WeixinAdapter

__all__ = [
    "FeishuAdapter",
    "FeishuQRSession",
    "WecomAdapter",
    "WecomQRSession",
    "WeixinAdapter",
]
