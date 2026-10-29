"""Soulprout 桌面端 sidecar。

桌面端本身只是云端 Agent 的一个界面；这个包负责「必须发生在用户电脑上」的那部分：

- ``local_tools``    在用户电脑上执行 read / write / edit / read_picture / bash，结果回给云端 Agent；
- ``policy`` / ``approvals``  本地工具的权限与用户审批（设计参考 deepseek-harness，见 desktop/NOTICE.md）；
- ``cloud_client``   与云端 ``/desktop/ws`` 的长连接（在线状态 + 接收工具调用）；
- ``server``         给桌面界面提供静态页面、云端 API 代理和本地会话的文件接口；
- ``gateway_host``   把原有 gateway（微信 / 飞书等渠道）作为桌面端的一部分运行。
"""

__version__ = "0.1.0"
