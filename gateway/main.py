"""
Gateway 服务入口。

main.py 的唯一职责是编排：
  1. 构建各平台 adapter
  2. 依次调用 connect()，让每个 adapter 自行启动它的 HTTP 服务器
  3. 等待退出信号（Ctrl+C / SIGTERM）
  4. 依次调用 disconnect() 优雅关闭

每个 adapter 自己管理：端口、HTTP 服务器、消息队列、Access Token 等。
main.py 不持有任何 FastAPI/uvicorn 实例。

启动方式：
    python gateway/main.py
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import List

# 保证以 `python gateway/main.py` 启动时也能正确解析顶层包
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from gateway.base import BasePlatformAdapter, MessageEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 消息处理器（业务逻辑入口）
# ---------------------------------------------------------------------------

async def on_message(event: MessageEvent) -> None:
    """
    所有平台的消息都汇聚到这里。

    event.source.platform  平台名称（如 "wecom_kf"）
    event.source.chat_id   会话 ID（如 "open_kfid:external_userid"）
    event.message_type     消息类型（TEXT / IMAGE / VOICE / ...）
    event.text             消息文本或媒体描述

    TODO: 将此处替换为你的业务逻辑，例如：
        reply = await call_agent(event.text)
        await adapter.send(event.source.chat_id, reply)
    """
    logger.info(
        "[Gateway] 收到消息 platform=%s chat=%s type=%s text=%r",
        event.source.platform if event.source else "unknown",
        event.source.chat_id if event.source else "unknown",
        event.message_type.value,
        event.text[:100],
    )


# ---------------------------------------------------------------------------
# 平台适配器注册
# ---------------------------------------------------------------------------

def build_adapters() -> List[BasePlatformAdapter]:
    """
    构建并返回所有已启用的平台 adapter 列表。

    每个 adapter 在 connect() 时自行启动 HTTP 服务器，端口各自独立。
    配置缺失的平台会打印警告并跳过，不影响其他平台正常运行。

    新增平台：在此函数末尾仿照下方模式追加即可。
    """
    adapters: List[BasePlatformAdapter] = []

    # ── 微信客服 ────────────────────────────────────────────────────────────
    try:
        from gateway.platforms.wecom_kf import WeComKFAdapter, WeComKFConfig
        config = WeComKFConfig.from_env()
        adapter = WeComKFAdapter(config)
        adapter.set_message_handler(on_message)
        adapters.append(adapter)
        logger.info(
            "[Gateway] 微信客服已注册，监听 %s:%d%s",
            config.host, config.port, config.callback_path,
        )
    except ValueError as exc:
        logger.warning("[Gateway] 微信客服未配置，跳过: %s", exc)

    # ── 新平台示例（取消注释并实现 XxxAdapter 即可）─────────────────────────
    # try:
    #     from gateway.platforms.xxx import XxxAdapter, XxxConfig
    #     config = XxxConfig.from_env()
    #     adapter = XxxAdapter(config)
    #     adapter.set_message_handler(on_message)
    #     adapters.append(adapter)
    #     logger.info("[Gateway] Xxx 已注册，监听 %s:%d", config.host, config.port)
    # except ValueError as exc:
    #     logger.warning("[Gateway] Xxx 未配置，跳过: %s", exc)

    return adapters


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run() -> None:
    adapters = build_adapters()

    if not adapters:
        logger.error("[Gateway] 没有任何 adapter 完成注册，请检查 .env 配置，退出")
        return

    # 启动所有 adapter
    connected: List[BasePlatformAdapter] = []
    for adapter in adapters:
        ok = await adapter.connect()
        if ok:
            connected.append(adapter)
        else:
            logger.error("[Gateway] %s 启动失败", adapter.platform)

    if not connected:
        logger.error("[Gateway] 所有 adapter 均启动失败，退出")
        return

    logger.info("[Gateway] 共 %d 个平台正在运行，按 Ctrl+C 退出", len(connected))

    # 等待退出信号
    stop_event = asyncio.Event()

    def _on_signal(*_):
        logger.info("[Gateway] 收到退出信号，正在关闭...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler，回退到 KeyboardInterrupt
            pass

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 优雅关闭
    for adapter in connected:
        await adapter.disconnect()
    logger.info("[Gateway] 已全部关闭")


if __name__ == "__main__":
    asyncio.run(run())
