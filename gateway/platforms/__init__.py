"""
Gateway 平台适配器模块。

已支持平台：
- wecom_kf  微信客服（企业微信对外客服，通过 sync_msg 拉取消息）

新增平台步骤：
1. 在本目录新建 <platform_name>.py
2. 继承 gateway.base.BasePlatformAdapter
3. 实现 connect / disconnect / send / get_chat_info 四个抽象方法
4. 在此文件中导出新类
"""

from gateway.platforms.wecom_kf import WeComKFAdapter, WeComKFConfig

__all__ = [
    "WeComKFAdapter",
    "WeComKFConfig",
]
