"""
Gateway 平台适配器模块。

已支持平台：
- weixin  个人微信（基于腾讯 iLink Bot API，扫码登录）

新增平台步骤：
1. 在本目录新建 <platform_name>.py
2. 继承 gateway.base.BasePlatformAdapter
3. 实现 connect / disconnect / send / get_chat_info 四个抽象方法
4. 在 gateway/main.py 中注册
"""

from gateway.platforms.weixin import WeixinAdapter

__all__ = [
    "WeixinAdapter",
]
