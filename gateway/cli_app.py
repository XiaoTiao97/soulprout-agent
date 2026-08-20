"""
Gateway 交互式 CLI：邮箱登录、选择平台、扫码或填写凭证。

由 ``bash gateway/run.sh config`` 或 ``python gateway/main.py --cli`` 启动。
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_PLATFORMS = (
    ("weixin", "微信（扫码）"),
    ("feishu", "飞书 / Lark（扫码或 App 凭证）"),
    ("wecom", "企业微信（扫码或 Bot 凭证）"),
    ("xiaoai", "小爱音箱（账号密码 / passToken）"),
    ("rokid", "Rokid AI 眼镜（生成接入凭证）"),
)


def _println(msg: str = "") -> None:
    print(msg, flush=True)


async def _ask(prompt: str, *, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    line = await asyncio.to_thread(input, f"{prompt}{suffix}: ")
    text = (line or "").strip()
    return text or default


async def _ask_yes_no(prompt: str, *, default_yes: bool = True) -> bool:
    hint = "Y/n" if default_yes else "y/N"
    ans = (await _ask(f"{prompt} ({hint})", default="Y" if default_yes else "N")).lower()
    if ans in ("y", "yes", "是", ""):
        return default_yes if ans == "" else True
    if ans in ("n", "no", "否"):
        return False
    return default_yes


async def _ask_secret(prompt: str, *, env_key: str = "") -> str:
    env_val = os.getenv(env_key, "").strip() if env_key else ""
    if env_val:
        _println(f"  已从 .env 读取 {prompt}")
        return env_val
    return (await asyncio.to_thread(getpass.getpass, f"{prompt}: ")).strip()


async def _prompt_or_env(label: str, env_key: str, *, secret: bool = False) -> str:
    env_val = os.getenv(env_key, "").strip()
    if env_val:
        _println(f"  已从 .env 读取 {label}（{env_key}）")
        return env_val
    if secret:
        return await _ask_secret(label, env_key=env_key)
    return await _ask(label)


async def ensure_agent_login(*, force: bool = False) -> bool:
    from gateway.agent_auth import login_with_email_code, send_email_code, verify_agent_session
    from gateway.config_store import get_agent_email, get_agent_url, get_default_agent_url

    if not force:
        check = await verify_agent_session()
        if check.get("ok"):
            label = check.get("email") or check.get("user_id") or "已登录"
            _println(f"\n✓ Soulprout 账号已登录：{label}")
            return True

    _println("\n── Soulprout 账号登录（邮箱验证码）──")
    _println("验证码将发送到您的邮箱；未注册的邮箱会自动创建账号。")

    official_url = get_default_agent_url()
    use_official = await _ask_yes_no(
        f"是否使用官网服务（{official_url}）",
        default_yes=True,
    )
    if use_official:
        agent_url = official_url
        _println(f"  使用官网：{agent_url}")
    else:
        _println("  将连接自部署 Agent；也可在 gateway/.env 中设置 AGENT_URL。")
        agent_url = await _ask("自部署 Agent 地址", default=get_agent_url() or "http://localhost:8080")
        agent_url = agent_url.rstrip("/")

    email = await _prompt_or_env("邮箱", "AGENT_EMAIL")
    if not email:
        _println("✗ 邮箱不能为空")
        return False

    send_result = await send_email_code(email=email, agent_url=agent_url)
    if not send_result.get("success"):
        _println(f"✗ {send_result.get('message') or send_result.get('msg') or '发送验证码失败'}")
        return False
    _println("✓ 验证码已发送，请查收邮件")

    code = await _ask("邮箱验证码")
    if not code:
        _println("✗ 验证码不能为空")
        return False

    login_result = await login_with_email_code(email=email, code=code, agent_url=agent_url)
    if not login_result.get("success"):
        _println(f"✗ {login_result.get('message') or login_result.get('msg') or '登录失败'}")
        return False

    _println(f"✓ 登录成功，用户 ID：{login_result.get('user_id', '')}")
    return True


async def _poll_qr_session(
    session: Any,
    *,
    scan_url_getter: Callable[[Dict[str, Any]], str],
    poll_interval: float = 2.0,
) -> bool:
    from gateway.terminal_qr import print_terminal_qr

    result = await session.start()
    if result.get("error"):
        _println(f"✗ {result['error']}")
        return False

    print_terminal_qr(scan_url_getter(result))
    _println("等待扫码确认…（Ctrl+C 可取消当前操作）")

    interval = float(getattr(session, "_interval", poll_interval) or poll_interval)
    while True:
        poll = await session.poll()
        status = poll.get("status")

        if status == "confirmed":
            _println("✓ 扫码绑定成功")
            await session.close()
            return True

        if status == "error":
            _println(f"✗ {poll.get('error') or '扫码失败'}")
            await session.close()
            return False

        if status == "refreshed":
            _println("\n二维码已过期并刷新，请重新扫描：")
            print_terminal_qr(scan_url_getter(poll))

        await asyncio.sleep(max(1.0, interval))


async def setup_weixin() -> bool:
    from gateway.platforms.weixin import QRLoginSession, list_weixin_accounts
    from gateway.web import _reconnect_weixin

    accounts = list_weixin_accounts()
    if accounts:
        reuse = await _ask_yes_no(f"检测到已有微信配置（{accounts[0]}），重新扫码绑定", default_yes=False)
        if not reuse:
            await _reconnect_weixin()
            return True

    _println("\n── 微信扫码绑定 ──")
    session = QRLoginSession()
    ok = await _poll_qr_session(session, scan_url_getter=lambda r: r.get("scan_url") or r.get("qrcode_value") or "")
    if ok:
        await _reconnect_weixin()
    return ok


async def setup_feishu() -> bool:
    from gateway.platforms.feishu import FeishuQRSession, has_feishu_config, probe_bot, save_feishu_config
    from gateway.web import _reconnect_feishu

    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    domain = os.getenv("FEISHU_DOMAIN", "feishu").strip() or "feishu"

    if has_feishu_config() or (app_id and app_secret):
        mode = await _ask(
            "飞书：1=扫码创建  2=手动填写/App凭证  3=使用已有配置直接连接",
            default="3" if has_feishu_config() else "1",
        )
    else:
        mode = await _ask("飞书：1=扫码创建（推荐）  2=手动填写 App ID/Secret", default="1")

    if mode == "3" and has_feishu_config():
        await _reconnect_feishu()
        _println("✓ 已尝试连接飞书")
        return True

    if mode == "2" or (app_id and app_secret and mode != "1"):
        if not app_id:
            app_id = await _ask("飞书 App ID")
        if not app_secret:
            app_secret = await _ask_secret("飞书 App Secret", env_key="FEISHU_APP_SECRET")
        if domain not in ("feishu", "lark"):
            domain = await _ask("平台域名 feishu 或 lark", default=domain)
        if not app_id or not app_secret:
            _println("✗ App ID 与 App Secret 不能为空")
            return False
        bot_info = await asyncio.to_thread(probe_bot, app_id, app_secret, domain) or {}
        save_feishu_config(
            app_id=app_id,
            app_secret=app_secret,
            domain=domain,
            bot_name=str(bot_info.get("bot_name") or ""),
            bot_open_id=str(bot_info.get("bot_open_id") or ""),
        )
        await _reconnect_feishu()
        _println("✓ 飞书凭证已保存并连接")
        return True

    _println("\n── 飞书扫码创建 Bot ──")
    if domain not in ("feishu", "lark"):
        domain = await _ask("平台域名 feishu 或 lark", default="feishu")
    session = FeishuQRSession(domain=domain)
    ok = await _poll_qr_session(session, scan_url_getter=lambda r: r.get("qr_url") or r.get("qrcode_url") or "")
    if ok:
        await _reconnect_feishu()
    return ok


async def setup_wecom() -> bool:
    from gateway.platforms.wecom import WecomQRSession, has_wecom_config, save_wecom_config
    from gateway.web import _reconnect_wecom

    bot_id = os.getenv("WECOM_BOT_ID", "").strip()
    secret = os.getenv("WECOM_SECRET", "").strip()

    if has_wecom_config() or (bot_id and secret):
        mode = await _ask(
            "企业微信：1=扫码获取  2=手动填写 Bot ID/Secret  3=使用已有配置直接连接",
            default="3" if has_wecom_config() else "1",
        )
    else:
        mode = await _ask("企业微信：1=扫码获取（推荐）  2=手动填写 Bot ID/Secret", default="1")

    if mode == "3" and has_wecom_config():
        await _reconnect_wecom()
        _println("✓ 已尝试连接企业微信")
        return True

    if mode == "2" or (bot_id and secret and mode != "1"):
        if not bot_id:
            bot_id = await _ask("企业微信 Bot ID")
        if not secret:
            secret = await _ask_secret("企业微信 Secret", env_key="WECOM_SECRET")
        if not bot_id or not secret:
            _println("✗ Bot ID 与 Secret 不能为空")
            return False
        save_wecom_config(bot_id=bot_id, secret=secret)
        await _reconnect_wecom()
        _println("✓ 企业微信凭证已保存并连接")
        return True

    _println("\n── 企业微信扫码绑定 ──")
    session = WecomQRSession()
    ok = await _poll_qr_session(
        session,
        scan_url_getter=lambda r: r.get("auth_url") or r.get("qr_url") or r.get("qrcode_url") or "",
    )
    if ok:
        await _reconnect_wecom()
    return ok


async def setup_xiaoai() -> bool:
    from gateway.platforms.xiaoai_miot import has_xiaoai_config, save_xiaoai_config, test_mina_login
    from gateway.web import _reconnect_xiaoai

    _println("\n── 小爱音箱配置 ──")
    _println("可在 gateway/.env 中预设：XIAOMI_USER_ID、XIAOMI_PASSWORD 或 XIAOMI_PASS_TOKEN、XIAOMI_DID")

    if has_xiaoai_config():
        reuse = await _ask_yes_no("检测到已有小爱配置，直接重新连接", default_yes=True)
        if reuse:
            await _reconnect_xiaoai()
            return True

    user_id = await _prompt_or_env("小米账号 ID", "XIAOMI_USER_ID")
    did = await _prompt_or_env("设备名称（did）", "XIAOMI_DID")
    password = await _prompt_or_env("小米密码（可留空若使用 passToken）", "XIAOMI_PASSWORD", secret=True)
    pass_token = await _prompt_or_env("passToken（可留空若使用密码）", "XIAOMI_PASS_TOKEN", secret=True)

    if not user_id or not did:
        _println("✗ 小米 ID 与设备名称不能为空")
        return False
    if not password and not pass_token:
        _println("✗ 请填写密码或 passToken 至少一项")
        return False

    _println("正在验证小米账号…")
    test = await test_mina_login(
        user_id=user_id,
        password=password,
        pass_token=pass_token,
        did=did,
    )
    if not test.get("success"):
        _println(f"✗ {test.get('message') or '登录失败'}")
        return False

    save_xiaoai_config(user_id=user_id, did=did, password=password, pass_token=pass_token)
    await _reconnect_xiaoai()
    _println(f"✓ 小爱配置成功：{test.get('device_name') or did}")
    return True


async def setup_rokid() -> bool:
    from gateway.platforms.rokid import ROKID_HOME_URL, ROKID_PUBLIC_SSE_URL
    from gateway.rokid_service import ensure_rokid_credentials

    _println("\n── Rokid AI 眼镜 ──")
    _println("Gateway 将为您生成接入凭证，请到 Rokid 开发者平台填写。")

    result = await ensure_rokid_credentials()
    if not result.get("success"):
        _println(f"✗ {result.get('error') or '生成失败'}")
        return False

    _println(f"\n✓ {result.get('message') or '凭证已就绪'}")
    _println("\n请在 Rokid 平台创建「三方智能体」时填写：")
    _println(f"  平台首页：{ROKID_HOME_URL}")
    _println(f"  自定义智能体 ID：{result.get('agent_id')}")
    _println(f"  自定义智能体 URL：{result.get('sse_url') or ROKID_PUBLIC_SSE_URL}")
    _println(f"  自定义智能体 AK：{result.get('api_key')}")
    _println("\n保存后，眼镜端即可通过主站 SSE 与 Soulprout 对话。")
    return True


def _platform_status_line(platform: str, label: str) -> str:
    from gateway.platform_registry import get_platform_adapter
    from gateway.platforms.feishu import has_feishu_config
    from gateway.platforms.wecom import has_wecom_config
    from gateway.platforms.weixin import list_weixin_accounts
    from gateway.platforms.xiaoai_miot import has_xiaoai_config
    from gateway.config_store import get_rokid_api_key, get_rokid_agent_id

    adapter = get_platform_adapter(platform)
    connected = bool(adapter and adapter.is_connected)

    configured = False
    if platform == "weixin":
        configured = bool(list_weixin_accounts())
    elif platform == "feishu":
        configured = has_feishu_config()
    elif platform == "wecom":
        configured = has_wecom_config()
    elif platform == "xiaoai":
        configured = has_xiaoai_config()
    elif platform == "rokid":
        configured = bool(get_rokid_api_key() and get_rokid_agent_id())

    if connected:
        state = "已连接"
    elif configured:
        state = "已配置，未连接"
    else:
        state = "未配置"

    return f"  {label}: {state}"


async def show_status() -> None:
    _println("\n── 平台连接状态 ──")
    for key, label in _PLATFORMS:
        _println(_platform_status_line(key, label))
    _println()


async def _run_menu_action(choice: str) -> None:
    handlers = {
        "1": setup_weixin,
        "2": setup_feishu,
        "3": setup_wecom,
        "4": setup_xiaoai,
        "5": setup_rokid,
    }
    handler = handlers.get(choice)
    if handler:
        try:
            await handler()
        except KeyboardInterrupt:
            _println("\n（已取消当前操作）")
        except Exception as exc:
            logger.error("CLI 平台配置异常: %s", exc, exc_info=True)
            _println(f"✗ 发生错误：{exc}")
        return

    if choice == "6":
        await show_status()
        return

    if choice == "7":
        await ensure_agent_login(force=True)
        return

    if choice == "0":
        return

    _println("无效选项，请重新输入。")


def _print_menu() -> None:
    _println("\n" + "─" * 40)
    _println("  Soulprout Gateway — 平台配置")
    _println("─" * 40)
    _println("  1. 连接微信（扫码）")
    _println("  2. 连接飞书 / Lark")
    _println("  3. 连接企业微信")
    _println("  4. 连接小爱音箱")
    _println("  5. 配置 Rokid AI 眼镜")
    _println("  6. 查看连接状态")
    _println("  7. 重新登录 Soulprout 账号")
    _println("  0. 完成配置并退出")
    _println("─" * 40)
    _println("配置过程中可即时测试连接；完成后输入 0 退出。")
    _println("退出后 run.sh 会询问是否后台启动（可安全关闭终端）。")
    _println("凭证也可写入 gateway/.env，下次会自动读取。\n")


async def run_interactive_menu(stop_event: asyncio.Event) -> None:
    """CLI 主菜单；选择 0 时设置 stop_event。"""
    await asyncio.sleep(0.5)

    if not await ensure_agent_login():
        _println("\n未登录 Soulprout 账号，Gateway 无法转发消息。请重新启动并完成登录。")
        stop_event.set()
        return

    _println("\n✓ 配置模式已就绪，请选择要连接的平台。")

    while not stop_event.is_set():
        _print_menu()
        try:
            choice = await _ask("请输入选项", default="")
        except (EOFError, KeyboardInterrupt):
            _println("\n收到退出信号…")
            stop_event.set()
            break

        if choice == "0":
            stop_event.set()
            _println("\n配置已保存。")
            _println("返回后将询问是否后台启动；也可稍后运行: bash gateway/run.sh start")
            break

        await _run_menu_action(choice)
